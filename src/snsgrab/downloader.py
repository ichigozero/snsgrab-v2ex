import os
import time

import requests
import youtube_dl

from . import log


class MediaDownloader:
    @staticmethod
    def construct_output_dirpath(
            sns_name,
            real_name,
            media,
            datetime
    ):
        sub_path = os.path.join(
            str(datetime.year),
            str(datetime.month).zfill(2)
        )

        return os.path.join(
            sns_name,
            real_name,
            media,
            sub_path,
        )

    @staticmethod
    def construct_output_filepath(
            sns_name,
            real_name,
            media,
            datetime,
            basename,
            file_ext=''
    ):
        sub_path = os.path.join(
            str(datetime.year),
            str(datetime.month).zfill(2)
        )
        filename = ''.join([basename, file_ext])

        return os.path.join(
            sns_name,
            real_name,
            media,
            sub_path,
            filename
        )

    @staticmethod
    def download(
            url,
            output_path,
            max_retry=5,
            retry_delay=5,
            retry_count=0
    ):
        is_saved = False

        if os.path.exists(output_path):
            existing_size = os.stat(output_path).st_size
        else:
            existing_size = 0

        try:
            resume_header = ({'Range': 'bytes={}-'.format(existing_size)})
            response = requests.get(
                url,
                headers=resume_header,
                stream=True,
                timeout=60
            )

            size_to_download = int(response.headers['Content-Length'])

            if size_to_download == 0:
                log.logger.info(
                    'File %s was already downloaded from %s',
                    output_path,
                    url
                )
            else:
                log.logger.info('Downloading %s', url)

                with open(output_path, 'ab') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                last_modified = response.headers.get('last-modified')

                # Match the downloaded media timestamp
                # with the timestamp listed on the server
                # for archiving purpose.
                if last_modified:
                    last_modified_in_epoch = time.mktime(
                        time.strptime(
                            last_modified,
                            '%a, %d %b %Y %H:%M:%S %Z'
                        )
                    )

                    os.utime(
                        output_path,
                        (last_modified_in_epoch, last_modified_in_epoch)
                    )

                log.logger.info('Download complete')

            is_saved = True
        except requests.exceptions.RequestException:
            if retry_count < max_retry:
                if retry_count == 0:
                    log.logger.warning('Attempting to re-download %s', url)

                log.logger.warning(
                    'Re-download attempt %d of %d',
                    retry_count + 1,
                    max_retry
                )
                time.sleep(retry_delay)
                MediaDownloader.download(
                    url,
                    output_path,
                    max_retry,
                    retry_delay,
                    retry_count + 1
                )
            else:
                log.logger.error('Unable to download %s', url)
                log.logger.error('The maximum retry count has been exceeded')

        return is_saved

    @staticmethod
    def download_with_youtube_dl(
            url,
            output_dirpath,
            max_retry=5,
            retry_delay=5,
            retry_count=0
    ):
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': ''.join([output_dirpath, '/', '%(id)s.%(ext)s'])
        }

        try:
            if retry_count == 0:
                log.logger.info('Downloading %s', url)

            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                output = ydl.extract_info(url, download=True)
                log.logger.info('Download complete')

                return ''.join(
                    [output['id'],
                     '.',
                     output['formats'][-1]['ext']]
                )
        except youtube_dl.utils.DownloadError:
            if retry_count < max_retry:
                if retry_count == 0:
                    log.logger.warning('Attempting to re-download %s', url)

                log.logger.warning(
                    'Re-download attempt %d of %d',
                    retry_count + 1,
                    max_retry
                )
                time.sleep(retry_delay)
                MediaDownloader.download_with_youtube_dl(
                    url,
                    output_dirpath,
                    max_retry,
                    retry_delay,
                    retry_count + 1
                )
            else:
                log.logger.error('Error occured when downloading %s', url)
                log.logger.error('The maximum retry count has been exceeded')

                return ''
