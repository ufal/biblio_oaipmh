#!/usr/bin/env bash

python import.py
cd ..
pserver biblio/biblio.ini &
curl http://127.0.0.1:6543/oai?verb=Identify
fg
