# platform = multi_platform_all
# packages = yum

sed -e '/RekeyLimit/d' /etc/ssh/sshd_config
echo "RekeyLimit 512M 2h" >> /etc/ssh/sshd_config
