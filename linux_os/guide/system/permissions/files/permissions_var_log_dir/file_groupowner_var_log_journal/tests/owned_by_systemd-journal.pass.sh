#!/bin/bash
# platform = Ubuntu 24.04

chown -R root /var/log

mkdir -p /var/log/journal/
touch /var/log/journal/test.journal
touch /var/log/journal/test.journal~
chgrp systemd-journal /var/log/journal/test.journal
chgrp systemd-journal /var/log/journal/test.journal~

