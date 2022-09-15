# platform = multi_platform_all
# reboot = false

# check if the system is UEFI
if ( [ -f /sys/firmware/efi ] ); then

function perform_remediation {
    mount_point_match_regexp="$(printf "[[:space:]]%s[[:space:]]" /boot/efi)"

    # If the mount point is not in /etc/fstab, get previous mount options from /etc/mtab
    if [ "$(grep -c "$mount_point_match_regexp" /etc/fstab)" -eq 0 ]; then
        # runtime opts without some automatic kernel/userspace-added defaults
        previous_mount_opts=$(grep "$mount_point_match_regexp" /etc/mtab | head -1 |  awk '{print $4}' \
                    | sed -E "s/(rw|defaults|seclabel|nosuid)(,|$)//g;s/,$//")
        [ "$previous_mount_opts" ] && previous_mount_opts+=","
        echo " /boot/efi  defaults,${previous_mount_opts}nosuid 0 0" >> /etc/fstab
    # If the mount_opt option is not already in the mount point's /etc/fstab entry, add it
    elif [ "$(grep "$mount_point_match_regexp" /etc/fstab | grep -c "nosuid")" -eq 0 ]; then
        previous_mount_opts=$(grep "$mount_point_match_regexp" /etc/fstab | awk '{print $4}')
        sed -i "s|\(${mount_point_match_regexp}.*${previous_mount_opts}\)|\1,nosuid|" /etc/fstab
    fi

    if mkdir -p "/boot/efi"; then
        if mountpoint -q "/boot/efi"; then
            mount -o remount --target "/boot/efi"
        else
            mount --target "/boot/efi"
        fi
    fi
}

perform_remediation

else
    >&2 echo 'Remediation is not applicable because the system is not UEFI, nothing was done'
fi
