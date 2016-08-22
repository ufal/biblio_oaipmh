# Biblio OAI-PMH Server

Used Kuha OAI-PMH server, see kuha.Readme.md and kuha.LICENSE.txt for more details.

## How to install

```
pip install -e .
```
This will install kuha and all the requirements in an editable mode (if it fails, try biblio/install.sh).


## How to start

Get data
```
cd biblio
svn --username XXX co https://svn.ms.mff.cuni.cz/svn/biblio/trunk biblio_from_svn
```
create symlinks
```
ln -s biblio_from_svn/xmldump input_biblio
```
and then import

```
./update.sh
```
which calls biblio/biblio_metadata_provider.py .

Nginx serving this web app may need path tweaking in kuha/oai/static


## OpenAIRE cached projects

These should be updated on a regular basis as well.
