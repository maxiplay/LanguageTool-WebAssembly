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

py cheerpj_1.3/cheerpjfy.py --deps=$libs target/ltwa-1.0-SNAPSHOT.jar


cp src/main/webapp/index.html target/

py -m http.server 8080

py -mwebbrowser http://localhot:8080


