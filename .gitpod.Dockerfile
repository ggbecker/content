FROM gitpod/workspace-full
USER gitpod
RUN sudo apt-get update -q && \
    sudo apt-get install -yq \
        cmake \
        ninja-build \
        libopenscap8 \
        libxml2-utils \
        expat \
        xsltproc \
        python3-jinja2 \
        python3-yaml \
        python3-setuptools \
        ansible-lint \
        python3-github \
        bats \
        python3-pytest \
        python3-pytest-cov

RUN pip install docker
