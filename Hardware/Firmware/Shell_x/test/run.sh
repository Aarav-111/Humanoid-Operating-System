#!/bin/bash
# Build and run the Shell x host tests. Needs a C++17 compiler (g++ or clang++). Set CXX to override.
set -e
cd "$(dirname "$0")"
CXX=${CXX:-c++}
mkdir -p traces build
$CXX -std=gnu++17 -O1 -Wall -Wno-unused-variable -Imock -c mock/mock.cpp -o build/mock.o
$CXX -std=gnu++17 -O1 -Wall -Imock -c tests.cpp -o build/tests.o
$CXX build/mock.o build/tests.o -o build/shellx_tests
./build/shellx_tests "$@"
