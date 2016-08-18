# Biblio OAI-PMH Server

Used Kuha OAI-PMH server, see kuha.Readme.md and kuha.LICENSE.txt for more details.

## How to install
 ```
 pip install -e .
 ```
 This will install kuha and all the requirements in an editable mode.


## How to start

Firstly, get data
```
svn update....
```

and then import data

```
python import.py
```

that calls biblio/biblio_metadata_provider.py

