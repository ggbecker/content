# platform = multi_platform_wrlinux,multi_platform_rhel,multi_platform_fedora,multi_platform_ol,multi_platform_rhv,multi_platform_sle

{{{ bash_instantiate_variables("var_accounts_passwords_pam_faillock_fail_interval") }}}

{{% macro remediation() -%}}
elif [ -f $FAILLOCK_CONF ]; then
    if $(grep -q '^\s*fail_interval\s*=' $FAILLOCK_CONF); then
        sed -i --follow-symlinks "s/^\s*\(fail_interval\s*\)=.*$/\1 = $var_accounts_passwords_pam_faillock_fail_interval/g" $FAILLOCK_CONF
    else
        echo "fail_interval = $var_accounts_passwords_pam_faillock_fail_interval" >> $FAILLOCK_CONF
    fi
    # If the faillock.conf file is present, but for any reason, like an OS upgrade, the
    # pam_faillock.so parameters are still defined in pam files, this makes them compatible with
    # the newer versions of authselect tool and ensure the parameters are only in faillock.conf.
    sed -i --follow-symlinks 's/\(pam_faillock.so preauth\).*$/\1 silent/g' $SYSTEM_AUTH $PASSWORD_AUTH
    sed -i --follow-symlinks 's/\(pam_faillock.so authfail\).*$/\1/g' $SYSTEM_AUTH $PASSWORD_AUTH
    authselect enable-feature with-faillock
else
    if [ -f /usr/sbin/authconfig ]; then
        authconfig --enablefaillock --update
    else
        authselect enable-feature with-faillock
    fi
    {{{ bash_set_faillock_option("fail_interval", "$var_accounts_passwords_pam_faillock_fail_interval") }}}
{{%- endmacro %}}

{{{ pam_faillock_stuff(remediation)  }}}
