#!/bin/bash
# platform = SUSE Linux Enterprise 15,multi_platform_fedora,multi_platform_ol,multi_platform_rhel,multi_platform_slmicro,multi_platform_almalinux
# packages = sudo

echo 'Defaults !targetpw' >> /etc/sudoers
echo 'Defaults !rootpw' >> /etc/sudoers
echo 'Defaults !runaspw' >> /etc/sudoers
# This wins
echo 'Defaults runaspw' >> /etc/sudoers
