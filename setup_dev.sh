#!/bin/bash
sudo apt-get update -q && \
    sudo apt-get install -yq \
    cmake \
    ninja-build \
    libxml2-utils \
    xsltproc \
    python3-jinja2 \
    python3-yaml \
    python3-setuptools \
    ansible-lint \
    python3-github \
    python3-pip \
    bats \
    python3-pytest \
    python3-pytest-cov \
    libdbus-1-dev libdbus-glib-1-dev libcurl4-openssl-dev \
    libgcrypt20-dev libselinux1-dev libxslt1-dev libgconf2-dev libacl1-dev libblkid-dev \
    libcap-dev libxml2-dev libldap2-dev libpcre3-dev python3-dev swig libxml-parser-perl \
    libxml-xpath-perl libperl-dev libbz2-dev librpm-dev g++ libapt-pkg-dev libyaml-dev \
    libxmlsec1-dev libxmlsec1-openssl \
    shellcheck \
    bats \
    yamllint

wget https://github.com/OpenSCAP/openscap/releases/download/1.3.6/openscap-1.3.6.tar.gz

tar -zxvf openscap-1.3.6.tar.gz

cd openscap-1.3.6 && \
    mkdir -p build && cd build && \
    cmake -DCMAKE_INSTALL_PREFIX=/ .. && \
    sudo make install && \
    cd ../..

pip install docker ansible json2html docutils==0.17.1 \
myst-parser \
sphinx \
sphinx-rtd-theme \
git+https://github.com/ggbecker/sphinxcontrib.jinjadomain.git#egg=sphinxcontrib-jinjadomain
[ -z "$PRODUCT" ] && PRODUCT="fedora"
[ -z "$CONTAINER" ] && CONTAINER=$PRODUCT
[ -z "$CONTAINER_VERSION" ] && CONTAINER_VERSION="$CONTAINER"
mkdir -p .vscode && cp .gitpod.launch.json .vscode/launch.json
CONTAINER_NAME=${CONTAINER}_container
sed -i "s/&&CONTAINER_NAME&&/$CONTAINER_NAME/g" .vscode/launch.json
sed -i "s/&&DEFAULT_PRODUCT&&/$PRODUCT/g" .vscode/launch.json
PRIVATE_KEY_FOLDER=.ssh
PRIVATE_KEY_FILEPATH=$PRIVATE_KEY_FOLDER/id_rsa
sed -i "s,&&PRIVATE_KEY_FILEPATH&&,$PRIVATE_KEY_FILEPATH,g" .vscode/launch.json
mkdir -p $PRIVATE_KEY_FOLDER
ssh-keygen -N '' -f $PRIVATE_KEY_FILEPATH
docker build --build-arg "CLIENT_PUBLIC_KEY=$(cat $PRIVATE_KEY_FILEPATH.pub)" -t $CONTAINER_NAME --build-arg IMAGE=$CONTAINER_VERSION -f Dockerfiles/test_suite-$CONTAINER .
[ -n "$WORKSHOP" ] && ansible-playbook -i 127.0.0.1, docs/workshop/labs_setup.yml -e EXERCISE=$WORKSHOP -e LAB_DIR=$GITPOD_REPO_ROOT --connection=local -u gitpod --ssh-extra-args '-F docs/workshop/data/ssh_config'
[ -z "$WORKSHOP" ] && ./build_product $PRODUCT --datastream-only
