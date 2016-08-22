#!/bin/bash
# - you should have biblio checkedout to biblio_from_svn and symlinked input/ to biblio_from_svn/xmldump
pushd biblio_from_svn
svn update
popd
python2.7 import.py

