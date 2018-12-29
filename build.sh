#!/bin/bash

echo "build.sh : maven build";

mvn clean install

echo "build.sh : cheerpj compilation begin";

py cheerpj_1.3/cheerpjfy.py --pack-jar=target/ltwa-1.0-SNAPSHOT-jar-with-dependencies.jar -j 10 target/ltwa-1.0-SNAPSHOT-jar-with-dependencies.jar >> build.log

echo "build.sh : Compilation finished";

cp src/main/webapp/index.html target/

cd target

echo "build.sh : start WebServer to port 8080";

py -m http.server 8080 &

py -mwebbrowser http://localhost:8080


read -p 'Type text to quit: ' uservar


