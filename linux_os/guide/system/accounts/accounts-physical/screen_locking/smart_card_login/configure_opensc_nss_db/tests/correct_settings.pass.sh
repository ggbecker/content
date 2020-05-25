#!/bin/bash

# profiles = xccdf_org.ssgproject.content_profile_ncp

yum install -y opensc nss-tools

modutil -delete "CoolKey PKCS #11 Module" -dbdir sql:/etc/pki/nssdb/ -force
modutil -add "OpenSC PKCS #11 Module" -dbdir sql:/etc/pki/nssdb/ -libfile opensc-pkcs11.so -force
