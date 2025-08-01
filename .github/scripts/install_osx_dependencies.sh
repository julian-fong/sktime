#!/bin/bash -e

# This script is used to build the system dependencies for MacOS
# It is called by test workflow in .github/workflows/
# To build necessary system dependencies for MacOS, run:

# check if os is MacOS using uname
if [ "$(uname)" = "Darwin" ]; then
    # install necessary dependencies
    echo "installing necessary dependencies..."
    brew install libomp

    LIBOMP_PREFIX="$(brew --prefix libomp)"

    echo "Verifying libomp installation..."
    ls "$LIBOMP_PREFIX/lib/libomp.dylib"

    {
        echo "DYLD_LIBRARY_PATH=$LIBOMP_PREFIX/lib:\$DYLD_LIBRARY_PATH"
        echo "LDFLAGS=-L$LIBOMP_PREFIX/lib"
        echo "CPPFLAGS=-I$LIBOMP_PREFIX/include"
    } >> "$GITHUB_ENV"
else
    echo "This script is intended to run on macOS (Darwin)."
fi
