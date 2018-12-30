#!/usr/bin/env python3

import bisect
import os
import shutil
from distutils.dir_util import copy_tree
import subprocess
from subprocess import PIPE, STDOUT
import tempfile
import time
import zipfile
import sys
import concurrent.futures
from optparse import OptionParser

parser = OptionParser()
parser.add_option("--split", dest="isSplit", help="Split generated JS into smaller modules", action="store_true")
parser.add_option("--no-runtime", dest="noRuntime", help="Do not automatically add the runtime to the class path", action="store_true")
parser.add_option("--precise-floats", dest="preciseFloats", help="Enable slow but accurate 32-bit float", action="store_true")
parser.add_option("--natives",dest="nativesPath", help="Root of the native implementations for classes in this JAR file", type="string", action="store")
parser.add_option("--deps",dest="depsPaths", help="List of ':' separated JARs that this JAR depends on", type="string", action="store")
parser.add_option("--work-dir",dest="workDir", help="Use a specific directory instead of a temporary one, it will not be cleared after the build is finised", type="string", action="store")
parser.add_option("--core-classes-list",dest="coreClassesList", help="File containing a list of classes that should be in the core module", type="string", action="store")
parser.add_option("--strip-jar",dest="stripJar", help="Generate a stripped version of the input JAR with all code replaced by nops for improved compression", type="string", action="store")
parser.add_option("--pack-jar",dest="packJar", help="Generate a packed version of the input JAR using the pack200 utility. Debug information and code are removed.", type="string", action="store")
parser.add_option("--stub-natives",dest="stubNatives", help="Generate stubs for all native methods for classes in this JAR", type="string", action="store")
parser.add_option("--pack-classes-list",dest="packClassesList", help="File containing a list of classes that should be compacted to the beginning and end of JAR file", type="string", action="store")
parser.add_option("--pack-strip-binaries",dest="packStripBinaries", help="Drop all dll/so/jnilib files from the JAR", action="store_true")
parser.add_option("--ignore-classes", dest="ignoreClasses", help="List of ',' separated classes that should not be compiled. Example --ignore-classes com.a.b.ClassOne,org.c.d.ClassTwo", type="string", action="store")
parser.add_option("-j",dest="numJobs", help="Number of parallel compilation jobs", type="int", action="store", default=1)
parser.add_option("-v", dest="doVersion", help="Dumps the version of the program and exists", action="store_true")
(option, args) = parser.parse_args()

BAD_CLASSES = ["COM/ibm/db2os390/sqlj/custom/DB2SQLJEntryInfo.class","java/time/chrono/HijrahChronology.class","java/time/chrono/HijrahDate.class","java/time/chrono/JapaneseChronology.class","java/time/chrono/JapaneseDate.class","java/time/chrono/MinguoChronology.class","java/time/chrono/MinguoDate.class","java/time/chrono/ThaiBuddhistChronology.class","java/time/chrono/ThaiBuddhistDate.class"]

versionId = "1.3";

if option.doVersion:
	print("CheerpJ %s" % versionId);
	print("Recommended loader:");
	print("\tNon-commercial users: https://cjrtnc.leaningtech.com/%s/loader.js" % versionId);
	print("\tCommercial users: https://cjrt.leaningtech.com/%s/loader.js" % versionId);
	exit(0)

if len(args) != 1 or not args[0].endswith(".jar"):
	print("Usage: %s file.jar" % sys.argv[0])
	exit(1)

if option.nativesPath and not os.path.isdir(option.nativesPath):
	print("--natives %s: Expected directory" % option.nativesPath)
	exit(1)

if option.workDir and not os.path.isdir(option.workDir):
	print("--work-dir %s: Expected directory" % option.workDir)
	exit(1)

if option.workDir and  option.stripJar:
	print("--work-dir incompatible with --strip-jar")
	exit(1)

if option.coreClassesList and not os.path.isfile(option.coreClassesList):
	print("--core-classes-list %s: Expected file" % option.coreClassesList)
	exit(1)

if option.stubNatives and not os.path.isdir(option.stubNatives):
	print("--stub-natives %s: Expected directory" % option.stubNatives)
	exit(1)

if option.packClassesList and not os.path.isfile(option.packClassesList):
	print("--pack-classes-list %s: Expected file" % option.packClassesList)
	exit(1)

if option.ignoreClasses:
	classList = option.ignoreClasses.split(",");
	for c in classList:
		c = c.replace('.','/') + ".class";
		BAD_CLASSES.append(c);

basePath = os.path.abspath(os.path.dirname(sys.argv[0]));
binPath = os.path.join(basePath, "bin");
cheerpPath = os.getenv('CHEERP_BL_PREFIX', os.path.join(basePath, "cheerp_bl"))

def unpackClassFiles(tempDir, jarFile, jarPath):
	jarName = os.path.basename(jarPath);
	jarUnpackPath = os.path.join(tempDir, "%s.dir" % jarName);
	# If we have natives copy them before unpacking so that copytree does not complain about the existing directory
	# NOTE: When compiling multiples JARs the natives will be copied everywhere, but they will only be used if the right class exists
	if option.nativesPath:
		copy_tree(option.nativesPath, jarUnpackPath);
	for f in jarFile.namelist():
		if not f.endswith(".class") or os.path.isfile(os.path.join(jarUnpackPath,f)):
			continue;
		jarFile.extract(f, jarUnpackPath);
	return jarUnpackPath;

class PackageSize:
	def __init__(self, path, size):
		self.path = path;
		self.size = size;
	def __lt__(self, other):
		# Order on the parent package, and if equal on size
		selfParent = os.path.dirname(self.path);
		otherParent = os.path.dirname(other.path);
		if selfParent < otherParent:
			return True;
		elif selfParent > otherParent:
			return False;
		else:
			return self.size < other.size;

class PackageInfo:
	def __init__(self):
		self.size = 0;
		self.files = set();

def appendAndCleanJS(baseClassName, jsLinesSet, jsOutput):
	for l in open(baseClassName+".js"):
		if l not in jsLinesSet:
			jsLinesSet.add(l);
			jsOutput.write(l);
	for l in open(baseClassName+"_llvm.js").readlines():
		if l not in jsLinesSet:
			jsLinesSet.add(l);
			jsOutput.write(l);
	# Delete JS
	if not option.workDir:
		os.remove(baseClassName+".js");
		os.remove(baseClassName+"_llvm.js");

executor = concurrent.futures.ThreadPoolExecutor(option.numJobs)
def compileClassFiles(cheerpj, cheerpjClassPath, tempDir, jarFile, jarPath, jsOutput, splitFiles):
	jarName = os.path.basename(jarPath);
	jarUnpackPath = os.path.join(tempDir, "%s.dir" % jarName);
	packageMap = dict();
	jsLines = set();
	def do_compile(f):
		if not f.endswith(".class"):
			return f, False;
		if f in BAD_CLASSES:
			return f, False;
		baseClassName = os.path.join(jarUnpackPath,f[:-6])
		js_time = os.path.getmtime(baseClassName+"_llvm.js") if os.path.isfile(baseClassName+"_llvm.js") else 0
		native_js_time = os.path.getmtime(baseClassName+"_native.js") if os.path.isfile(baseClassName+"_native.js") else 0
		class_time = os.path.getmtime(baseClassName+".class") if os.path.isfile(baseClassName+".class") else 0
		if class_time <= js_time and native_js_time <= js_time:
			print("skipping",f,"...")
			return f, True
		print("compiling",f,"...")
		# We need to use Popen to change the current directory
		p = subprocess.Popen([cheerpj, "-precise-floats" if option.preciseFloats else "", "-llvm", "-llvm-exceptions", "-cp", cheerpjClassPath, f], cwd=jarUnpackPath,stdout=PIPE, stderr=STDOUT);
		out,_ = p.communicate();
		ret = p.returncode
		if ret != 0:
			print("Failure compiling %s" % f)
			print("command: "+subprocess.list2cmdline(p.args))
			print(out.decode('utf-8'))
			return f, False;
		# Optimize LLVM code that has been generated for supported methods
		p = subprocess.Popen([cheerpPath+"/bin/opt","-march=cheerp","-O2","%s_llvm.bc" % baseClassName,"-o","%s_llvm.opted.bc" % baseClassName], cwd=jarUnpackPath, stdout=PIPE, stderr=STDOUT);
		out,_ = p.communicate()
		ret = p.returncode;
		if ret != 0:
			print("Failure compiling %s" % f)
			print("command: "+subprocess.list2cmdline(p.args))
			print(out.decode('utf-8'))
			return f, False;
		# Generate JS code from the optimized LLVM code
		p = subprocess.Popen([cheerpPath+"/bin/llc","-march=cheerp","-cheerp-reserved-names=a,b,f,i,p","-cheerp-no-boilerplate","%s_llvm.opted.bc" % baseClassName,"-o","%s_llvm.js" % baseClassName], cwd=jarUnpackPath, stdout=PIPE, stderr=STDOUT);
		out,_ = p.communicate()
		ret = p.returncode;
		if ret != 0:
			print("Failure compiling %s" % f)
			print("command: "+subprocess.list2cmdline(p.args))
			print(out.decode('utf-8'))
			return f, False;
		if option.stubNatives:
			nativePath = os.path.split(os.path.join(option.stubNatives,f))[0];
			if not os.path.isdir(nativePath):
				os.makedirs(nativePath);
			cheerpjNativeStub = os.path.join(binPath, "cheerpj-native-stub")
			p = subprocess.Popen([cheerpjNativeStub, f, os.path.splitext(os.path.join(os.path.abspath(option.stubNatives),f))[0]+"_native.js"], cwd=jarUnpackPath, stdout=PIPE, stderr=STDOUT);
			out,_ = p.communicate();
		return f, True
	for f, compiled in executor.map(do_compile, jarFile.namelist()):
		if not compiled:
			if f[:-6] in coreClasses:
				coreClasses.remove(f[:-6])
			continue
		baseClassName = os.path.join(jarUnpackPath, f[:-6])
		# Append compiled JS file to output
		if not splitFiles:
			appendAndCleanJS(baseClassName, jsLines, jsOutput);
		elif f[:-6] not in coreClasses:
			# Core classes are added in the main module
			jsName = baseClassName+".js";
			llvmName = baseClassName+"_llvm.js";
			packageName = os.path.dirname(f);
			if not packageName in packageMap:
				packageMap[packageName] = PackageInfo();
			jsSize = os.path.getsize(jsName);
			llvmSize = os.path.getsize(llvmName)
			packageMap[packageName].size += jsSize + llvmSize;
			packageMap[packageName].files.add(baseClassName);

	if not splitFiles:
		return;

	existingPackages = sorted(packageMap.keys())
	currentPackageIndex = len(existingPackages);
	while currentPackageIndex > 0:
		p = existingPackages[currentPackageIndex-1];
		parentPackage = os.path.dirname(p);
		if parentPackage == "":
			currentPackageIndex -= 1;
			continue;
		if not parentPackage in existingPackages:
			# Insert the package at the right position
			insertPos = bisect.bisect_left(existingPackages, parentPackage)
			assert insertPos < currentPackageIndex;
			currentPackageIndex+=1;
			existingPackages.insert(insertPos, parentPackage);
			packageMap[parentPackage] = PackageInfo();
		packageMap[parentPackage].size += packageMap[p].size;
		packageMap[parentPackage].files |= packageMap[p].files;
		currentPackageIndex-=1;
		
	packagesAndSizes = []
	existingPackages = sorted(packageMap.keys())
	for p in existingPackages:
		packagesAndSizes.append(PackageSize(p, packageMap[p].size));

	packagesAndSizes.sort(reverse=True)
	
	jsOutput.write("cheerpjAOTPackages['%s']=[" % jarName);
	firstPackage = True;
	for p in packagesAndSizes:
		print("PACKAGE %s SIZE %u" % (p.path, p.size));
	for p in packagesAndSizes:
		parentPackage = os.path.dirname(p.path);
		jsPackageLines = set();
		if parentPackage != "" and packageMap[parentPackage].size <= 1024*1024:
			# TODO: Merge the output in the parent and move on
			pass
		else:
			if packageMap[p.path]:
				print("MAKE PACKAGE FOR %s SIZE %u" % (p.path, packageMap[p.path].size));
				jsPackage = open(jarPath + "." + p.path.replace('/','.') + ".js", "w");
				jsPackage.write("cheerpjCL={cl:null};\n");
				if firstPackage == False:
					jsOutput.write(",");
				jsOutput.write("'%s/'" % p.path);
				firstPackage = False;
				for f in packageMap[p.path].files:
					appendAndCleanJS(f, jsPackageLines, jsPackage);
				jsPackage.close();
			# Subtract this child from the parent and move on
			while parentPackage != "":
				packageMap[parentPackage].size -= packageMap[p.path].size;
				packageMap[parentPackage].files -= packageMap[p.path].files;
				parentPackage = os.path.dirname(parentPackage);
	
	jsOutput.write("]\n");
	for c in coreClasses:
		appendAndCleanJS(os.path.join(jarUnpackPath,c), jsLines, jsOutput);
	return

def makeStrippedJar(cheerpjstrip, tempDir, jarFile, jarPath, stripJarPath):
	jarName = os.path.basename(jarPath);
	jarUnpackPath = os.path.join(tempDir, "%s.dir" % jarName);
	strippedJar = zipfile.ZipFile(stripJarPath, "w", zipfile.ZIP_DEFLATED);
	for f in jarFile.namelist():
		if not f.endswith(".class"):
			# Directly copy the file
			strippedJar.writestr(f, jarFile.read(f));
			continue;
		# We need to use Popen to change the current directory
		p = subprocess.Popen([cheerpjstrip, f], cwd=jarUnpackPath);
		ret = p.wait();
		if ret != 0:
			print("Failure stripping %s" % f)
			# The .class file may be invalid now, so get it again from the original archive
			strippedJar.writestr(f, jarFile.read(f));
			continue;
		# TODO: Put all core classes at the end
		strippedJar.write(os.path.join(jarUnpackPath, f), f);

def makePackedJar(jarFile, jarPath, packedJarPath, packClasses):
	print("Packing JAR %s" % jarPath);
	if packClasses:
		# Make a new JAR with the listed files before all the others
		with tempfile.NamedTemporaryFile(suffix='.jar') as tempJarFile:
			tempJar = zipfile.ZipFile(tempJarFile, "w", zipfile.ZIP_DEFLATED);
			for c in packClasses:
				tempJar.writestr(c, jarFile.read(c));
			# Put all resources at the end
			# TODO: We need a better strategy to distribute contents between the beginning and the end of the file
			resFiles = [];
			for f in jarFile.namelist():
				# Skip the files we have already put in front
				if f in packClasses:
					continue;
				if option.packStripBinaries and (f.endswith(".dll") or f.endswith(".so") or f.endswith(".jnilib")):
					continue;
				if not f.endswith(".class"):
					resFiles.append(f);
					continue;
				tempJar.writestr(f, jarFile.read(f));
			for r in resFiles:
				tempJar.writestr(r, jarFile.read(r));
			tempJar.close();
			print("Using tmp "+tempJarFile.name)
			p = subprocess.Popen(["pack200", "--method-attribute=Code=strip", "--field-attribute=ConstantValue=strip", "-G", "-r", packedJarPath, tempJarFile.name]);
			ret = p.wait();
			if ret != 0:
				print("Failure packing %s" % f)
	else:
		p = subprocess.Popen(["pack200", "--method-attribute=Code=strip", "--field-attribute=ConstantValue=strip", "-G", "-r", packedJarPath, jarPath]);
		ret = p.wait();
		if ret != 0:
			print("Failure packing %s" % f)

def getManifestProperty(jarFile, propertyName):
	# Get information from the manifest if any
	m = jarFile.open("META-INF/MANIFEST.MF")
	if m == None:
		return None;
	# The manifest format joins line if the start with a space
	ret = None;
	for l in m:
		l = l.decode("utf-8").rstrip("\n\r");
		# Join the lines if we already found tag
		if ret != None:
			if l.startswith(" "):
				ret += l[1:];
				continue
			else:
				return ret;
		propertyTag = "%s: " % propertyName;
		if l.startswith(propertyTag):
			ret = l[len(propertyTag):]
	return None;

def runOnDir(tempDir):
	mainJar = args[0]
	mainJarPath = os.path.dirname(mainJar);
	jarFile = zipfile.ZipFile(mainJar);
	classPath = getManifestProperty(jarFile, "Class-Path");
	# Unpack the rt.jar archive
	if not option.noRuntime:
		rtPath = os.path.join(basePath,"rt.jar");
		rtFile = zipfile.ZipFile(rtPath);
		rtClassPath = unpackClassFiles(tempDir, rtFile, rtPath);
		cheerpjClassPath = os.path.join(rtClassPath, "");
	else:
		cheerpjClassPath = "";
	jarsToCompile = [mainJar];
	if classPath:
		#We need to unpack all classes from all referenced jars and add the directories to the cheerpj classpath
		for usedJarPath in classPath.split(" "):
			if not usedJarPath.endswith(".jar"):
				continue;
			usedJarPath = os.path.join(mainJarPath,usedJarPath);
			try:
				usedJarFile = zipfile.ZipFile(usedJarPath);
			except FileNotFoundError:
				continue
			unpackPath = unpackClassFiles(tempDir, usedJarFile, usedJarPath);
			cheerpjClassPath += ":" + unpackPath;
			if option.stripJar or option.packJar:
				print("Can't compile dependent jar %s while using --strip-jar" % usedJarPath);
			else:
				jarsToCompile.append(usedJarPath);
	if option.depsPaths:
		for usedJarPath in option.depsPaths.split(":"):
			try:
				usedJarFile = zipfile.ZipFile(usedJarPath);
			except FileNotFoundError:
				continue
			unpackPath = unpackClassFiles(tempDir, usedJarFile, usedJarPath);
			cheerpjClassPath += ":" + os.path.join(unpackPath, "");
	# Unpack the main jar
	unpackClassFiles(tempDir, jarFile, mainJar);

	# Now compile all needed jars
	cheerpjCompiler = os.path.join(binPath, "cheerpj");
	if option.stripJar or option.packJar:
		assert(len(jarsToCompile)==1);
	for jarPath in jarsToCompile:
		print("Compiling jar ",jarPath)
		jsOutput = open(jarPath + ".js", "w");
		jsOutput.write("/*Compiled using CheerpJ (R) %s by Leaning Technologies Ltd*/\n" % versionId);
		jsOutput.write("cheerpjCL={cl:null};\n");
		jarFile = zipfile.ZipFile(jarPath);
		compileClassFiles(cheerpjCompiler, cheerpjClassPath, tempDir, jarFile, jarPath, jsOutput, option.isSplit);
		if option.stripJar:
			makeStrippedJar(os.path.join(binPath, "cheerpj-strip"), tempDir, jarFile, jarPath, option.stripJar);
		if option.packJar:
			makePackedJar(jarFile, jarPath, option.packJar, packClasses);

coreClasses = []
packClasses = None;

if option.coreClassesList:
	coreClassesList = open(option.coreClassesList);
	for l in coreClassesList:
		coreClasses.append(l.strip())

if option.packClassesList:
	packClasses = []
	packClassesList = open(option.packClassesList);
	for l in packClassesList:
		packClasses.append(l.strip()+".class")

if option.workDir:
	fullWorkDir = os.path.abspath(option.workDir)
	runOnDir(fullWorkDir);
else:
	# Create a managed temporary directory that will disapper when the context end
	with tempfile.TemporaryDirectory() as tempDir:
		runOnDir(tempDir);

exit(0);
