# platform = multi_platform_fedora,Red Hat Enterprise Linux 8,Red Hat Enterprise Linux 9

{{% macro remediation() -%}}
else
    if [ ! $(grep -q '^\s*local_users_only' $FAILLOCK_CONF) ]; then
        echo "local_users_only" >> $FAILLOCK_CONF
    fi
    authselect enable-feature with-faillock
{{%- endmacro %}}

{{{ pam_faillock_stuff(remediation)  }}}
