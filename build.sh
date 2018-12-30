#!/bin/bash

mvn clean install

cd target/libs

libs='';
for file in * ; do

    crt="$file";
    libs="$libs:target/libs/$crt";

done

echo "$libs";

cd ../../

py cheerpj_1.3/cheerpjfy.py -j 10 --deps=$libs target/ltwa-1.0-SNAPSHOT.jar >> build.log

cp src/main/webapp/index.html target/

cd target

py -mwebbrowser http://localhost:8080

py -m http.server 8080


