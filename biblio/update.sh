#!/bin/bash
# - you should have biblio checkedout to biblio_from_svn and symlinked input/ to biblio_from_svn/xmldump
export LC_CTYPE=en_US.UTF-8
pushd biblio_from_svn
svn update
popd
python import.py

