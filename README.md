# About
SNS post grabber and media downloader.

This program will scrape twitter and instagram posts and medias
(images and videos).

# Requirements
This program has been tested in environment with the following configuration:

- Python 3.7.3
- MongoDB 4.4.2
- Chromium 87.0.4280.141
- Chromedriver 87.0.4280.141

# Installation

```bash
   $ python3 -m venv venv
   $ source venv/bin/activate
   $ pip3 install .
```

# Usage

## Scraping instagram posts to database

```bash
   $ snsgrab instagram-to-db [OPTIONS] REAL_NAME ACCOUNT_NAME
```

Where,
- `REAL_NAME` is the actual name of the account holder
- `ACCOUNT_NAME` is Instagram username

Example

```bash
   $ snsgrab instagram-to-db 山田太郎 ytaro
```

### OPTIONS

```
   -h, --help                       Print this help text and exit
   -p, --pause                      Scraping pause interval in seconds
   -hl, --headless                  Run the program in headless mode.
                                    The default value is True.
   -ud, --until_date                Only scrape posts with timestamp newer
                                    than unti_date value
   -H, --host                       MongoDB hostname
   -P, --port                       MongoDB port number
   -l, --login                      Instagram login ID
   -pw, --password                  Instagram password
```

## Scraping twitter posts to database

```bash
   $ snsgrab twitter-to-db [OPTIONS] REAL_NAME MEDIA
```

Where,
- `REAL_NAME` is the actual name of the account holder
- `MEDIA` is either `image` or `video`

Example

```bash
   $ snsgrab twitter-to-db -fa ytaro 山田太郎 image
```

### OPTIONS

```
   -h, --help                       Print this help text and exit
   -p, --pause                      Scraping pause interval in seconds
   -hl, --headless                  Run the program in headless mode.
                                    The default value is True.
   -aw, --all_words                 Include posts containing all the words
   -ew, --exact_words               Include posts containing the exact words
   -iw, --include_words             Include posts which contain specified words
   -ew, --exclude_words             Exclude posts which contain specified words
   -ht, --hashtags                  Include posts for given hashtags
   -fa, --from_account              Scrape posts from specified user
   -ta, --to_account                Scrape posts which addressed to specified user
   -m, --mentions                   Include posts which contain given mentions
   -sd, --since_date                Scrape posts not older than `since_date`
   -ud, --until_date                Scrape posts not newer than `until_date`
   -H, --host                       MongoDB hostname
   -P, --port                       MongoDB port number
```

# License

MIT
