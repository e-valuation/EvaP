DART_SASS_STANDALONE_URL="https://github.com/sass/dart-sass/releases/download/1.32.0/dart-sass-1.32.0-linux-x64.tar.gz"
wget $DART_SASS_STANDALONE_URL --no-verbose --output-document - | sudo tar --extract --gzip --directory /usr/local/bin --strip-components 1
