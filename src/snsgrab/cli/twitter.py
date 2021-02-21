import csv
import datetime
import os
import time
import urllib.parse
from calendar import monthrange

import click
import pymongo
from dateutil.parser import isoparse
from pymongo import MongoClient
from pyvirtualdisplay import Display

from .common import export_collection_of_post_details
from snsgrab import log
from snsgrab.downloader import MediaDownloader
from snsgrab.scraper import TwitterScraper

DL_MAX_RETRY = 10


@click.command()
@click.option('--pause', '-p', default=5)
@click.option('--headless', '-hl', default=True, type=bool)
@click.option('--all_words', '-aw', default='')
@click.option('--exact_words', '-ew', default='')
@click.option('--include_words', '-iw', default='')
@click.option('--exclude_words', '-ew', default='')
@click.option('--hashtags', '-ht', default='')
@click.option('--from_account', '-fa', default='')
@click.option('--to_account', '-ta', default='')
@click.option('--mentions', '-m', default='')
@click.option('--since_date', '-sd', default='')
@click.option('--until_date',
              '-ud',
              default=datetime.datetime.now().strftime('%Y-%m-%d'))
@click.argument('real_name')
@click.argument('media')
def twitter(
        pause,
        headless,
        all_words,
        exact_words,
        include_words,
        exclude_words,
        hashtags,
        from_account,
        to_account,
        mentions,
        since_date,
        until_date,
        real_name,
        media
):
    if media not in ('image', 'video'):
        raise ValueError('Media is either image or video!')

    sns_name = 'twitter'

    log.setup_logger(sns_name, real_name)
    scraper = TwitterScraper(scroll_pause_time=pause)

    # Scraping tweets over long time range would require
    # high RAM consumption which could cause the browser to crash.
    if since_date:
        date_ranges = split_date_range_to_month_chunks(since_date, until_date)
    else:
        date_ranges = [[since_date, until_date]]

    display = None

    if headless:
        display = Display().start()

    try:
        scraper.launch_browser()

        post_details = {'0': []}

        for date_range in date_ranges:
            url_parameters = {
                'all_words': all_words,
                'exact_words': exact_words,
                'include_words': include_words,
                'exclude_words': exclude_words,
                'hashtags': hashtags,
                'from_account': from_account,
                'to_account': to_account,
                'mentions': mentions,
                'since': date_range[0],
                'until': get_next_day_date(date_range[1]),
            }

            post_details['0'].extend(
                scraper.get_collection_of_post_details(
                    url_parameters,
                    media
                )['0']
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

            if detail['images']:
                failed_download['images'] = []

                for image in detail['images']:
                    filepath = MediaDownloader.construct_output_filepath(
                        sns_name=sns_name,
                        real_name=real_name,
                        media='image',
                        datetime=isoparse(detail['submit_time']),
                        basename=image['basename'],
                        file_ext='.jpg'
                    )
                    dirpath = os.path.dirname(filepath)

                    os.makedirs(dirpath, exist_ok=True)

                    # Sometimes image in original size cannot be
                    # downloaded for some reasons. As work around,
                    # try re-downloading up to certain count.
                    # If retry count is reached, download the image
                    # without original flag.
                    is_saved = MediaDownloader.download(
                        url=''.join([image['url'], ':orig']),
                        output_path=filepath,
                        max_retry=DL_MAX_RETRY
                    )

                    if not is_saved:
                        is_saved = MediaDownloader.download(
                            url=image['url'],
                            output_path=filepath,
                            max_retry=DL_MAX_RETRY
                        )

                        if not is_saved:
                            failed_download['images'].append(image)

                if failed_download['images']:
                    failed_downloads.append(failed_download)
            elif detail['video_url']:
                failed_download['videos'] = []

                dirpath = MediaDownloader.construct_output_dirpath(
                    sns_name=sns_name,
                    real_name=real_name,
                    media='video',
                    datetime=isoparse(detail['submit_time']),
                )

                os.makedirs(dirpath, exist_ok=True)

                absolute_url = urllib.parse.urljoin(
                    'https://www.twitter.com',
                    detail['video_url']
                )

                print()  # youtube-dl output breaks progress bar
                filename = MediaDownloader.download_with_youtube_dl(
                    url=absolute_url,
                    output_dirpath=dirpath
                )

                if not filename:
                    failed_download['videos'].append(detail)

        if failed_downloads:
            post_details['3'] = failed_downloads

        export_collection_of_post_details(
            post_details,
            sns_name,
            real_name,
            log.logger
        )


@click.command()
@click.option('--pause', '-p', default=5)
@click.option('--headless', '-hl', default=True, type=bool)
@click.option('--all_words', '-aw', default='')
@click.option('--exact_words', '-ew', default='')
@click.option('--include_words', '-iw', default='')
@click.option('--exclude_words', '-ew', default='')
@click.option('--hashtags', '-ht', default='')
@click.option('--from_account', '-fa', default='')
@click.option('--to_account', '-ta', default='')
@click.option('--mentions', '-m', default='')
@click.option('--since_date', '-sd', default='')
@click.option('--until_date',
              '-ud',
              default=datetime.datetime.now().strftime('%Y-%m-%d'))
@click.option('--host', '-H', default='localhost')
@click.option('--port', '-P', default=27017)
@click.argument('real_name')
@click.argument('media')
def twitter_to_db(
        pause,
        headless,
        all_words,
        exact_words,
        include_words,
        exclude_words,
        hashtags,
        from_account,
        to_account,
        mentions,
        since_date,
        until_date,
        host,
        port,
        real_name,
        media
):
    if media not in ('image', 'video'):
        raise ValueError('Media is either image or video!')

    sns_name = 'twitter'

    log.setup_logger(sns_name, real_name)
    scraper = TwitterScraper(scroll_pause_time=pause)

    client = MongoClient(host, port)
    db = client.twitter
    posts = db.posts
    posts.create_index([('post_id', pymongo.ASCENDING)], unique=True)

    # Scraping tweets over long time range would require
    # high RAM consumption which could cause the browser to crash.
    if since_date:
        date_ranges = split_date_range_to_month_chunks(since_date, until_date)
    else:
        date_ranges = [[since_date, until_date]]

    display = None

    if headless:
        display = Display().start()

    try:
        scraper.launch_browser()

        post_details = {'0': []}

        for date_range in date_ranges:
            url_parameters = {
                'all_words': all_words,
                'exact_words': exact_words,
                'include_words': include_words,
                'exclude_words': exclude_words,
                'hashtags': hashtags,
                'from_account': from_account,
                'to_account': to_account,
                'mentions': mentions,
                'since': date_range[0],
                'until': get_next_day_date(date_range[1]),
            }

            post_details['0'].extend(
                scraper.get_collection_of_post_details(
                    url_parameters,
                    media
                )['0']
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
            post = {
                'post_id': detail['tweet_id'],
                'user': real_name,
                'timestamp': detail['submit_time'],
                'text': detail['tweet_text'],
            }

            failed_download = dict(detail)

            if detail['images']:
                failed_download['images'] = []

                post['media'] = []

                for image in detail['images']:
                    post['media'].append({
                        'type': 'image',
                        'filename': ''.join([image['basename'], '.jpg']),
                    })

                    filepath = MediaDownloader.construct_output_filepath(
                        sns_name=sns_name,
                        real_name=real_name,
                        media='image',
                        datetime=isoparse(detail['submit_time']),
                        basename=image['basename'],
                        file_ext='.jpg'
                    )
                    dirpath = os.path.dirname(filepath)

                    os.makedirs(dirpath, exist_ok=True)

                    # Sometimes image in original size cannot be
                    # downloaded for some reasons. As work around,
                    # try re-downloading up to certain count.
                    # If retry count is reached, download the image
                    # without original flag.
                    is_saved = MediaDownloader.download(
                        url=''.join([image['url'], ':orig']),
                        output_path=filepath,
                        max_retry=DL_MAX_RETRY
                    )

                    if not is_saved:
                        is_saved = MediaDownloader.download(
                            url=image['url'],
                            output_path=filepath,
                            max_retry=DL_MAX_RETRY
                        )

                        if not is_saved:
                            failed_download['images'].append(image)

                if failed_download['images']:
                    failed_downloads.append(failed_download)
            elif detail['video_url']:
                failed_download['videos'] = []

                dirpath = MediaDownloader.construct_output_dirpath(
                    sns_name=sns_name,
                    real_name=real_name,
                    media='video',
                    datetime=isoparse(detail['submit_time']),
                )

                os.makedirs(dirpath, exist_ok=True)

                absolute_url = urllib.parse.urljoin(
                    'https://www.twitter.com',
                    detail['video_url']
                )

                print()  # youtube-dl output breaks progress bar
                filename = MediaDownloader.download_with_youtube_dl(
                    url=absolute_url,
                    output_dirpath=dirpath
                )

                post['media'] = {'type': 'video', 'filename': filename}

                if not filename:
                    failed_download['videos'].append(detail)

            try:
                posts.insert_one(post)
            except pymongo.errors.DuplicateKeyError:
                log.logger.warning('Trying to insert duplicate post into DB')

        if failed_downloads:
            post_details['3'] = failed_downloads

        export_collection_of_post_details(
            post_details,
            sns_name,
            real_name,
            log.logger
        )


def split_date_range_to_month_chunks(since_date, until_date):
    parsed_since_date = datetime.datetime.strptime(since_date, '%Y-%m-%d')
    parsed_until_date = datetime.datetime.strptime(until_date, '%Y-%m-%d')
    delta = parsed_until_date - parsed_since_date
    date_ranges = []

    if delta.days == 0:
        date_ranges.append([since_date, until_date])

    while delta.days > 0:
        days_in_month = monthrange(
            parsed_since_date.year,
            parsed_since_date.month
        )[1]

        if delta.days > days_in_month:
            date_ranges.append([
                parsed_since_date.strftime('%Y-%m-%d'),
                datetime.datetime(
                    parsed_since_date.year,
                    parsed_since_date.month,
                    days_in_month
                ).strftime('%Y-%m-%d')
            ])
            parsed_since_date = (
                parsed_since_date.replace(day=1)
                + datetime.timedelta(days=days_in_month)
            )
        else:
            date_ranges.append([
                parsed_since_date.strftime('%Y-%m-%d'),
                until_date
            ])
            parsed_since_date = parsed_until_date

        delta = parsed_until_date - parsed_since_date

    return date_ranges


def get_next_day_date(input_date):
    parsed_input_date = datetime.datetime.strptime(input_date, '%Y-%m-%d')
    next_day_date = parsed_input_date + datetime.timedelta(days=1)

    return next_day_date.strftime('%Y-%m-%d')
