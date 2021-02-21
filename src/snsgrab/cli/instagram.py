import csv
import datetime
import os
import sys
import pickle
import time

import click
import pymongo
from pymongo import MongoClient
from pyvirtualdisplay import Display

from .common import export_collection_of_post_details
from snsgrab import log
from snsgrab.downloader import MediaDownloader
from snsgrab.scraper import InstagramScraper

DL_MAX_RETRY = 10


@click.command()
@click.option('--pause', '-p', default=5)
@click.option('--headless', '-hl', default=True, type=bool)
@click.option('--until_date', '-ud', default='')
@click.option('--login', '-l', default='')
@click.option('--password', '-pw', default='')
@click.argument('real_name')
@click.argument('account_name')
def instagram(
        pause,
        headless,
        until_date,
        login,
        password,
        real_name,
        account_name
):
    sns_name = 'instagram'

    log.setup_logger(sns_name, account_name)
    scraper = InstagramScraper(scroll_pause_time=pause)

    if until_date:
        parsed_until_date = (
            datetime
            .datetime
            .strptime(until_date, '%Y-%m-%d')
        )
    else:
        parsed_until_date = None

    display = None

    if headless:
        display = Display().start()

    try:
        scraper.launch_browser()

        if login and password:
            scraper.login(username=login, password=password)

        post_details = scraper.get_collection_of_post_details(
            account_name,
            parsed_until_date
        )
    finally:
        scraper.terminate_browser()

        if headless:
            display.stop()

    failed_downloads = []

    with click.progressbar(
            post_details['0'],
            label='Download %'
    ) as bar:
        for detail in bar:
            failed_download = dict(detail)
            failed_download['media'] = []

            for media in detail['media']:
                filepath = MediaDownloader.construct_output_filepath(
                    sns_name=sns_name,
                    real_name=real_name,
                    media=media['type'],
                    datetime=(
                        datetime
                        .datetime
                        .fromtimestamp(detail['timestamp'])
                    ),
                    basename=media['basename'],
                    file_ext=media['file_ext']
                )
                dirpath = os.path.dirname(filepath)

                os.makedirs(dirpath, exist_ok=True)
                is_saved = MediaDownloader.download(
                    url=media['url'],
                    output_path=filepath,
                    max_retry=DL_MAX_RETRY
                )

                if not is_saved:
                    failed_download['media'].append(media)

            if failed_download['media']:
                failed_downloads.append(failed_download)

    if failed_downloads:
        post_details['2'] = failed_downloads

    export_collection_of_post_details(
        post_details,
        sns_name,
        real_name,
        log.logger
    )


@click.command()
@click.option('--pause', '-p', default=5)
@click.option('--headless', '-hl', default=True, type=bool)
@click.option('--save-to-db', '-db', default=True, type=bool)
@click.option('--fetch-limit', '-sl', default=10)
@click.option('--host', '-H', default='localhost')
@click.option('--port', '-P', default=27017)
@click.option('--login', '-l', default='')
@click.option('--password', '-pw', default='')
@click.argument('real_name')
@click.argument('pickle_path')
def instagram_re(
        pause,
        headless,
        save_to_db,
        fetch_limit,
        host,
        port,
        login,
        password,
        real_name,
        pickle_path
):
    sns_name = 'instagram_re'

    log.setup_logger(sns_name, real_name)
    scraper = InstagramScraper(scroll_pause_time=pause)

    def log_post_details_count(post_details):
        log.logger.info(
            'Done: %d posts',
            len(post_details.get('0', []))
        )
        log.logger.info(
            'Fetch Error: %d posts',
            len(post_details.get('1', []))
        )
        log.logger.info(
            'Download Error: %d posts',
            len(post_details.get('2', []))
        )

    try:
        with open(pickle_path, mode='rb') as f:
            imported_post_details = pickle.load(f)

            log.logger.info(
                'Loaded pickle object from %s',
                pickle_path
            )
            log_post_details_count(imported_post_details)
    except IOError:
        log.logger.error(
            'Unable to load pickle object from %s',
            pickle_path
        )
        sys.exit()

    dump_details = {'0': imported_post_details['0'].copy()}

    # Target posts for re-fetch attempt might have been deleted.
    # To avoid useless re-fetch attempt for same posts over and over
    # it is best to move remaining failed post details fetch to beginning
    # and move failed re-fetch post details to the end.
    post_details = {
        '0': [],
        '1': imported_post_details['1'][fetch_limit:]
    }

    if len(imported_post_details['1']) > 0:
        try:
            display = None

            if headless:
                display = Display().start()

            scraper.launch_browser()

            if login and password:
                scraper.login(username=login, password=password)

            with click.progressbar(
                imported_post_details['1'][:fetch_limit],
                label='Fetching post details %'
            ) as bar:
                for post_url in bar:
                    refetched_details = scraper.get_post_details(post_url)

                    if post_details is not None:
                        post_details['0'].append(refetched_details)
                    else:
                        post_details['1'].append(post_url)

                    time.sleep(pause)
        finally:
            scraper.terminate_browser()

            if headless:
                display.stop()

    if save_to_db:
        client = MongoClient(host, port)
        db = client.instagram
        posts = db.posts
        posts.create_index([('post_id', pymongo.ASCENDING)], unique=True)

        with click.progressbar(
                post_details['0'],
                label='Saving post details %'
        ) as bar:
            for detail in bar:
                post = {
                    'post_id': detail['id'],
                    'user': real_name,
                    'timestamp': detail['timestamp'],
                    'location': detail['location'],
                    'text': detail['text'],
                    'media': [],
                }

                for media in detail['media']:
                    post['media'].append({
                        'type': media['type'],
                        'filename': ''.join(
                            [media['basename'],
                             media['file_ext']]
                        ),
                    })

                try:
                    posts.insert_one(post)
                except pymongo.errors.DuplicateKeyError:
                    log.logger.warning(
                        'Trying to insert duplicate post into DB'
                    )

    failed_downloads = []

    try:
        download_details = (
            post_details['0']
            + imported_post_details['2']
        )
    except KeyError:
        download_details = post_details['0']

    with click.progressbar(
            download_details,
            label='Downloading media %'
    ) as bar:
        for detail in bar:
            failed_download = dict(detail)
            failed_download['media'] = []

            for media in detail['media']:
                filepath = MediaDownloader.construct_output_filepath(
                    sns_name=sns_name,
                    real_name=real_name,
                    media=media['type'],
                    datetime=(
                        datetime
                        .datetime
                        .fromtimestamp(detail['timestamp'])
                    ),
                    basename=media['basename'],
                    file_ext=media['file_ext']
                )
                dirpath = os.path.dirname(filepath)

                os.makedirs(dirpath, exist_ok=True)
                is_saved = MediaDownloader.download(
                    url=media['url'],
                    output_path=filepath,
                    max_retry=DL_MAX_RETRY
                )

                if not is_saved:
                    failed_download['media'].append(media)

            if failed_download['media']:
                failed_downloads.append(failed_download)

    dump_details['0'] += post_details['0']
    dump_details['1'] = post_details['1'].copy()

    if failed_downloads:
        dump_details['2'] = failed_downloads

    try:
        with open(pickle_path, mode='wb') as f:
            pickle.dump(dump_details, f)

            log.logger.info(
                'Exported pickle object to %s',
                pickle_path
            )
            log_post_details_count(dump_details)
    except IOError:
        log.logger.error(
            'Unable to write pickle object to %s',
            pickle_path
        )


@click.command()
@click.option('--pause', '-p', default=5)
@click.option('--headless', '-hl', default=True, type=bool)
@click.option('--until_date', '-ud', default='')
@click.option('--host', '-H', default='localhost')
@click.option('--port', '-P', default=27017)
@click.option('--login', '-l', default='')
@click.option('--password', '-pw', default='')
@click.argument('real_name')
@click.argument('account_name')
def instagram_to_db(
        pause,
        headless,
        until_date,
        host,
        port,
        login,
        password,
        real_name,
        account_name
):
    sns_name = 'instagram'

    log.setup_logger(sns_name, real_name)
    scraper = InstagramScraper(scroll_pause_time=pause)

    client = MongoClient(host, port)
    db = client.instagram
    posts = db.posts
    posts.create_index([('post_id', pymongo.ASCENDING)], unique=True)

    if until_date:
        parsed_until_date = (
            datetime
            .datetime
            .strptime(until_date, '%Y-%m-%d')
        )
    else:
        parsed_until_date = None

    display = None

    if headless:
        display = Display().start()

    try:
        scraper.launch_browser()

        if login and password:
            scraper.login(username=login, password=password)

        post_details = scraper.get_collection_of_post_details(
            account_name,
            parsed_until_date
        )
    finally:
        scraper.terminate_browser()

        if headless:
            display.stop()

    failed_downloads = []

    with click.progressbar(
            post_details['0'],
            label='Download %'
    ) as bar:
        for detail in bar:
            failed_download = dict(detail)
            failed_download['media'] = []

            post = {
                'post_id': detail['id'],
                'user': real_name,
                'timestamp': detail['timestamp'],
                'location': detail['location'],
                'text': detail['text'],
                'media': [],
            }

            for media in detail['media']:
                post['media'].append({
                    'type': media['type'],
                    'filename': ''.join(
                        [media['basename'],
                         media['file_ext']]
                    ),
                })

            try:
                posts.insert_one(post)
            except pymongo.errors.DuplicateKeyError:
                log.logger.warning('Trying to insert duplicate post into DB')
                # Assume that if post has be recorded in the DB,
                # the media has already been downloaded in the past.
                continue

            for media in detail['media']:
                filepath = MediaDownloader.construct_output_filepath(
                    sns_name=sns_name,
                    real_name=real_name,
                    media=media['type'],
                    datetime=(
                        datetime
                        .datetime
                        .fromtimestamp(detail['timestamp'])
                    ),
                    basename=media['basename'],
                    file_ext=media['file_ext']
                )
                dirpath = os.path.dirname(filepath)

                os.makedirs(dirpath, exist_ok=True)
                is_saved = MediaDownloader.download(
                    url=media['url'],
                    output_path=filepath,
                    max_retry=DL_MAX_RETRY
                )

                if not is_saved:
                    failed_download['media'].append(media)

            if failed_download['media']:
                failed_downloads.append(failed_download)

    if failed_downloads:
        post_details['2'] = failed_downloads

    export_collection_of_post_details(
        post_details,
        sns_name,
        real_name,
        log.logger
    )


@click.command()
@click.option('--pause', '-p', default=5)
@click.option('--headless', '-hl', default=True, type=bool)
@click.option('--until_date', '-ud', default='')
@click.option('--host', '-H', default='localhost')
@click.option('--port', '-P', default=27017)
@click.option('--login', '-l', default='')
@click.option('--password', '-pw', default='')
@click.argument('account_list_csv')
def instagram_to_db_batch(
        pause,
        headless,
        until_date,
        host,
        port,
        login,
        password,
        account_list_csv
):
    sns_name = 'instagram'
    scraper = None

    client = MongoClient(host, port)
    db = client.instagram
    posts = db.posts
    posts.create_index([('post_id', pymongo.ASCENDING)], unique=True)

    if until_date:
        parsed_until_date = (
            datetime
            .datetime
            .strptime(until_date, '%Y-%m-%d')
        )
    else:
        parsed_until_date = None

    current_time = datetime.datetime.now().time()
    current_hour = current_time.hour
    current_minute = current_time.minute

    if current_minute < 30:
        scrape_time = current_hour
    else:
        scrape_time = current_hour + 0.5

    scrape_time = str(scrape_time)

    display = None

    if headless:
        display = Display().start()

    try:
        with open(account_list_csv, mode='r') as csv_file:
            csv_reader = csv.DictReader(csv_file)

            for row in csv_reader:
                if row['scrape_time'] != scrape_time:
                    continue

                real_name = row['real_name']
                account_name = row['account_name']

                log.setup_logger(sns_name, real_name)

                if scraper is None:
                    scraper = InstagramScraper(scroll_pause_time=pause)
                    scraper.launch_browser()

                    if login and password:
                        scraper.login(username=login, password=password)

                post_details = scraper.get_collection_of_post_details(
                    account_name,
                    parsed_until_date
                )

                failed_downloads = []

                with click.progressbar(
                        post_details['0'],
                        label='Download %'
                ) as bar:
                    for detail in bar:
                        failed_download = dict(detail)
                        failed_download['media'] = []

                        post = {
                            'post_id': detail['id'],
                            'user': real_name,
                            'timestamp': detail['timestamp'],
                            'location': detail['location'],
                            'text': detail['text'],
                            'media': [],
                        }

                        for media in detail['media']:
                            post['media'].append({
                                'type': media['type'],
                                'filename': ''.join(
                                    [media['basename'],
                                     media['file_ext']]
                                ),
                            })

                        try:
                            posts.insert_one(post)
                        except pymongo.errors.DuplicateKeyError:
                            log.logger.warning(
                                'Trying to insert duplicate post into DB'
                            )
                            # Assume that if post has be recorded in the DB,
                            # the media has already been downloaded
                            # in the past.
                            continue

                        for media in detail['media']:
                            filepath = (
                                MediaDownloader.construct_output_filepath(
                                    sns_name=sns_name,
                                    real_name=real_name,
                                    media=media['type'],
                                    datetime=(
                                        datetime
                                        .datetime
                                        .fromtimestamp(detail['timestamp'])
                                    ),
                                    basename=media['basename'],
                                    file_ext=media['file_ext']
                                )
                            )
                            dirpath = os.path.dirname(filepath)

                            os.makedirs(dirpath, exist_ok=True)
                            is_saved = MediaDownloader.download(
                                url=media['url'],
                                output_path=filepath,
                                max_retry=DL_MAX_RETRY
                            )

                            if not is_saved:
                                failed_download['media'].append(media)

                            time.sleep(5) # Avoid spamming request

                        if failed_download['media']:
                            failed_downloads.append(failed_download)

                if failed_downloads:
                    post_details['2'] = failed_downloads

                export_collection_of_post_details(
                    post_details,
                    sns_name,
                    real_name,
                    log.logger
                )

                time.sleep(60)
    finally:
        if scraper is not None:
            scraper.terminate_browser()

        if headless:
            display.stop()
