import datetime
import json
import re
import requests
import time
from abc import ABCMeta
from abc import abstractmethod

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from . import log

BROWSER_TIMEOUT = 60


class SnsScraper(metaclass=ABCMeta):
    def __init__(self, scroll_pause_time=5):
        self._scroll_pause_time = scroll_pause_time
        self._webdriver = None
        self._scraped_post_urls = set()

    def launch_browser(self, *args, **kwargs):
        def _get_browser_options():
            options = webdriver.ChromeOptions()
            options.add_argument("--incognito")
            options.add_experimental_option(
                'prefs',
                {'profile.managed_default_content_settings.images': 2}
            )

            return options

        self._webdriver = webdriver.Chrome(options=_get_browser_options())

    @abstractmethod
    def _compose_url(self, *args, **kwargs):
        return ''

    def _get_page_soups(self):
        last_page_source = ''
        scroll_height = 0
        client_height = self._webdriver.execute_script(
            'return document.documentElement.clientHeight;'
        )
        max_scroll_reached = False

        # Make sure page is fully loaded before
        # performing scrolling operation.
        time.sleep(self._scroll_pause_time)

        while True:
            if self._webdriver.page_source != last_page_source:
                last_page_source = self._webdriver.page_source
                yield BeautifulSoup(last_page_source, 'html.parser')

            if max_scroll_reached:
                break

            scroll_height = scroll_height + client_height

            self._webdriver.execute_script(
                'window.scrollTo(0, {});'.format(str(scroll_height)))

            max_scroll_height = self._webdriver.execute_script(
                'return Math.max('
                'document.body.scrollHeight, '
                'document.documentElement.scrollHeight,'
                'document.body.offsetHeight, '
                'document.documentElement.offsetHeight,'
                'document.body.clientHeight, '
                'document.documentElement.clientHeight'
                ');'
            )

            if scroll_height >= max_scroll_height:
                max_scroll_reached = True
            else:
                time.sleep(self._scroll_pause_time)

    def _scroll_element_into_center_of_view(self, element):
        if self._webdriver is None:
            raise AttributeError('Launch the browser first!')

        script = (
            'var viewPortHeight = Math.max('
            'document.documentElement.clientHeight, '
            'window.innerHeight || 0); '
            'var elementTop = arguments[0].getBoundingClientRect().top; '
            'window.scrollBy(0, elementTop-(viewPortHeight/2));'
        )

        self._webdriver.execute_script(script, element)

    @abstractmethod
    def get_collection_of_post_details(self, *args, **kwargs):
        pass

    @classmethod
    def _print_scraping_status(cls, scroll_count, scraped_url_count):
        message = '\rScrolled {} time(s), {} post(s) scraped'
        print(message.format(scroll_count, scraped_url_count), end='')

    @abstractmethod
    def _get_page_elements(self, *args, **kwargs):
        pass

    def terminate_browser(self):
        try:
            self._webdriver.quit()
            self._webdriver = None
        except AttributeError:
            log.logger.exception('Webdriver has not been initialized')


class InstagramScraper(SnsScraper):
    def __init__(self, scroll_pause_time=5):
        super().__init__(scroll_pause_time)

    def _compose_url(self, account_name):
        return 'https://www.instagram.com/{}/'.format(account_name)

    def login(self, username, password):
        login_url = 'https://www.instagram.com/accounts/login/'

        log.logger.info('Login to instagram via %s', login_url)
        self._webdriver.get(login_url)

        try:
            WebDriverWait(self._webdriver, BROWSER_TIMEOUT).until(
                EC.presence_of_all_elements_located((By.NAME, 'username'))
            )

            input_user = self._webdriver.find_element_by_name('username')
            input_pass = self._webdriver.find_element_by_name('password')

            input_user.send_keys(username)
            input_pass.send_keys(password)

            self._webdriver.find_element_by_css_selector('.L3NKy').click()
        except TimeoutException:
            log.logger.error('Loading login page took to much time')
        except NoSuchElementException:
            log.logger.error('Login form element not found')
        else:
            try:
                WebDriverWait(self._webdriver, BROWSER_TIMEOUT).until(
                    EC.url_changes(login_url)
                )
                log.logger.info('Logged in to instagram')
            except TimeoutException:
                log.logger.error('Login timeout')

    def get_collection_of_post_details(
            self,
            account_name,
            until_date=None
    ):
        if self._webdriver is None:
            raise AttributeError('Launch the browser first!')

        account_url = self._compose_url(account_name)

        print('Scraping {}'.format(account_url))
        log.logger.info('Scraping %s', account_url)

        self._webdriver.get(account_url)
        soup = BeautifulSoup(self._webdriver.page_source, 'html.parser')

        try:
            total_posts = soup.find('span', class_='g47SY').text
            total_posts = int(total_posts.replace(',', ''))
        except AttributeError:
            # Continue the process even if total post count
            # cannot be scraped due to changes in HTML source.
            total_posts = 0
            log.logger.warning('Unable to fetch post count')

        soup_count = 0
        output = {'0': [], '1': []}
        stop_scrolling = False

        for soup_count, soup in enumerate(self._get_page_soups(), start=1):
            self._print_scraping_status(
                scroll_count=soup_count,
                scraped_url_count=len(self._scraped_post_urls)
            )

            for post_url in self._get_page_elements(soup):
                post_details = self.get_post_details(post_url)

                try:
                    if until_date:
                        post_datetime = (
                            datetime
                            .datetime
                            .fromtimestamp(post_details['timestamp'])
                        )
                        if post_datetime < until_date:
                            stop_scrolling = True
                            break
                except TypeError:
                    # Avoid scraping all post if post datetime
                    # cannot be determined
                    log.logger.error(
                        'Unable to determine post timestamp. Aborting...'
                    )
                    stop_scrolling = True
                    break

                self._print_scraping_status(
                    scroll_count=soup_count,
                    scraped_url_count=len(self._scraped_post_urls)
                )

                if post_details is not None:
                    output['0'].append(post_details)
                else:
                    output['1'].append(post_url)

                # Avoid sending too many requests for
                # JSON post details in short time span
                time.sleep(self._scroll_pause_time)

            if ((total_posts > 0
                 and len(self._scraped_post_urls) == total_posts)
                    or stop_scrolling):
                break

        log.logger.info('Page scrolled %d time(s)', soup_count)
        log.logger.info('URL scraped %d time(s)', len(self._scraped_post_urls))
        log.logger.info(
            'Post scraped %d time(s)',
            len(output['0']) + len(output['1'])
        )

        # "_print_scraping_status" method prints messages without new line.
        # Thus, a new line needs to be printed to fix the subsequent
        # printed message presentation.
        print()

        # Clean up for subsequent method calls
        self._scraped_post_urls.clear()

        return output

    def _get_page_soups(self):
        yield from super()._get_page_soups()

        # Instagram only show several posts unless user clicks
        # "View More Post" button at the end of the page.
        try:
            xpath = '//div[contains(@class, "_7UhW9")]'
            element = self._webdriver.find_element_by_xpath(xpath)

            self._scroll_element_into_center_of_view(element)
            element.click()

            log.logger.info('"View More Post" button has been clicked')

            yield from super()._get_page_soups()
        except NoSuchElementException:
            log.logger.warning('"View More Post" button not found')

    def _get_page_elements(self, soup):
        for article in soup.find_all('article'):
            for a_tag in article.find_all('a'):
                post_url = a_tag['href']

                if post_url not in self._scraped_post_urls:
                    self._scraped_post_urls.add(post_url)
                    yield post_url

    def get_post_details(self, post_url):
        def _get_video_media_details(node):
            return {
                'url': node['video_url'],
                'type': 'video',
                'basename': node['shortcode'],
                'file_ext': '.mp4'
            }

        def _get_image_media_details(node):
            return {
                'url': node['display_url'],
                'type': 'image',
                'basename': node['shortcode'],
                'file_ext': '.jpg'
            }

        absolute_url = 'https://www.instagram.com{}?__a=1'.format(post_url)
        log.logger.info('Fetching post details from %s', absolute_url)

        try:
            json_data = self._get_post_json_data(absolute_url)
            media = json_data['graphql']['shortcode_media']

            output = {
                'id':  media['id'],
                'location': media['location'],
                'timestamp': media['taken_at_timestamp'],
                'post_url': post_url
            }

            if media['__typename'] == 'GraphVideo':
                output['media'] = [_get_video_media_details(media)]
            elif media['__typename'] == 'GraphImage':
                output['media'] = [_get_image_media_details(media)]
            elif media['__typename'] == 'GraphSidecar':
                output_media = []

                for edge in media['edge_sidecar_to_children']['edges']:
                    if edge['node']['__typename'] == 'GraphVideo':
                        output_media.append(
                            _get_video_media_details(edge['node'])
                        )
                    else:
                        output_media.append(
                            _get_image_media_details(edge['node'])
                        )

                output['media'] = output_media

            try:
                output['text'] = (
                    media['edge_media_to_caption']['edges'][0]['node']['text']
                )
            except IndexError:
                output['text'] = None
                log.logger.warning('Post body not available')

            log.logger.info('Fetch complete')

            return output
        except KeyError as e:
            log.logger.error(
                'Key %s not found in %s JSON response',
                str(e),
                absolute_url
            )

        return None

    def _get_post_json_data(self, post_url):
        if self._webdriver is None:
            raise AttributeError('Launch the browser first!')

        self._webdriver.execute_script(
            'window.open("{}", "_blank");'.format(post_url)
        )
        self._webdriver.switch_to_window(self._webdriver.window_handles[1])

        post_json = {}

        try:
            wait = WebDriverWait(self._webdriver, BROWSER_TIMEOUT)
            wait.until(
                EC.presence_of_all_elements_located((By.TAG_NAME, 'pre'))
            )

            json_text = self._webdriver.find_element_by_tag_name('pre').text
            post_json = json.loads(json_text)
        except TimeoutException:
            log.logger.error('Loading %s to much time', post_url)
        except NoSuchElementException:
            log.logger.error('Element with JSON data missing in %s', post_url)
        except json.decoder.JSONDecodeError:
            log.logger.error('Unable to decode JSON data from %s', post_url)
        finally:
            self._webdriver.close()
            self._webdriver.switch_to.window(self._webdriver.window_handles[0])

        return post_json


class TwitterScraper(SnsScraper):
    def _compose_url(self, url_parameters, media=''):
        base_url = 'https://twitter.com/search?q='
        url_parts = []

        for key, value in url_parameters.items():
            if not value:
                continue

            if key == 'all_words':
                url_part = '{}'.format(value)
            elif key == 'exact_words':
                url_part = '"{}"'.format(value)
            elif key == 'include_words':
                url_part = '({})'.format(value.replace(' ', ' OR '))
            elif key == 'exclude_words':
                url_part = '-{}'.format(value.replace(' ', ' -'))
            elif key == 'hashtags':
                url_part = '(%23{})'.format(value.replace(' ', ' OR %23'))
            elif key == 'from_account':
                url_part = '(from:{})'.format(value.replace(' ', ' OR from:'))
            elif key == 'to_account':
                url_part = '(to:{})'.format(value.replace(' ', ' OR to:'))
            elif key == 'mentions':
                url_part = '(%40{})'.format(value.replace(' ', ' OR %40'))
            elif key in ('since', 'until'):
                url_part = '{}:{}'.format(key, value)

            url_parts.append(url_part)

        if media:
            url_parts.append('&f={}'.format(media))

        return ''.join([base_url, '%20'.join(url_parts)])

    def get_collection_of_post_details(
            self,
            url_parameters,
            media
    ):
        if media not in ('image', 'video'):
            raise ValueError('Media is either image or video!')

        if self._webdriver is None:
            raise AttributeError('Launch the browser first!')

        twitter_url = self._compose_url(url_parameters, media)

        print('Scraping {}'.format(twitter_url))
        log.logger.info('Scraping %s', twitter_url)

        self._webdriver.get(twitter_url)
        soup = BeautifulSoup(self._webdriver.page_source, 'html.parser')

        soup_count = 0
        output = {'0': []}

        for soup_count, soup in enumerate(self._get_page_soups(), start=1):
            self._print_scraping_status(
                scroll_count=soup_count,
                scraped_url_count=len(self._scraped_post_urls)
            )

            for tweet_details in self._get_page_elements(soup):
                self._print_scraping_status(
                    scroll_count=soup_count,
                    scraped_url_count=len(self._scraped_post_urls)
                )

                output['0'].append(tweet_details)

        log.logger.info('Page scrolled %d time(s)', soup_count)
        log.logger.info(
            'Post scraped %d time(s)',
            len(self._scraped_post_urls)
        )
        log.logger.info('URL scraped %d time(s)', len(output['0']))

        # "_print_scraping_status" method prints messages without new line.
        # Thus, a new line needs to be printed to fix the subsequent
        # printed message presentation.
        print()

        # Clean up for subsequent method calls
        self._scraped_post_urls.clear()

        return output

    def _get_page_elements(self, soup):
        for tweet in soup.find_all('article', class_='r-1loqt21'):
            tweet_url = (
                tweet
                .find('a',
                      class_='css-4rbku5',
                      href=re.compile('.*/status/.*'))
                .get('href')
            )

            submit_time = tweet.find('time').get('datetime')

            if tweet_url not in self._scraped_post_urls:
                self._scraped_post_urls.add(tweet_url)

                tweet_soup = self._get_individual_tweet_soup(tweet_url)

                if tweet_soup is None:
                    continue

                try:
                    tweet_text = (
                        tweet_soup
                        .find('div', class_='css-1dbjc4n r-156q2ks')
                        .get_text(strip=True)
                    )
                except AttributeError:
                    tweet_text = ''
                    log.logger.warning('Unable to scrape tweet text')

                image_details = self._get_submitted_image_details(tweet_soup)

                if self._has_video(tweet_soup):
                    video_url = tweet_url
                else:
                    video_url = ''

                page_elements = {
                    'tweet_id': tweet_url.rsplit('/', 1)[1],
                    'tweet_text': tweet_text,
                    'images': image_details,
                    'video_url': video_url,
                    'submit_time': submit_time,
                }

                yield page_elements

    def _get_individual_tweet_soup(self, tweet_url):
        if self._webdriver is None:
            raise AttributeError('Launch the browser first!')

        self._webdriver.execute_script(
            'window.open("{}", "_blank");'.format(tweet_url)
        )
        self._webdriver.switch_to_window(self._webdriver.window_handles[1])

        try:
            # Assume the page is fully loaded
            # if post timestamp is visible
            wait = WebDriverWait(self._webdriver, BROWSER_TIMEOUT)

            elements = (
                (By.CLASS_NAME, 'css-901oao'),
                (By.CLASS_NAME, 'css-16my406'),
                (By.CLASS_NAME, 'r-1tl8opc'),
                (By.CLASS_NAME, 'r-ad9z0x'),
                (By.CLASS_NAME, 'r-bcqeeo'),
                (By.CLASS_NAME, 'r-qvutc0'),
            )

            for element in elements:
                wait.until(EC.presence_of_all_elements_located(element))

            safety_span_xpath = (
                '//a[contains(@class, "css-4rbku5") '
                'and contains(@href, "/settings/safety")]'
                '/../../following-sibling::div[1]'
                '//span/span'
            )

            # Twitter sometimes hide medias included in tweet
            # which considered sensitive.
            # To unhide it user must click the corresponding element.
            try:
                safety_span = (
                    self
                    ._webdriver
                    .find_element_by_xpath(safety_span_xpath)
                )

                self._scroll_element_into_center_of_view(safety_span)
                safety_span.click()
                log.logger.info('"Safety" button has been clicked')
                time.sleep(1)
            except NoSuchElementException:
                pass

            soup = BeautifulSoup(self._webdriver.page_source, 'html.parser')
        except TimeoutException:
            log.logger.error('Loading %s to much time', tweet_url)
            soup = None
        finally:
            self._webdriver.close()
            self._webdriver.switch_to.window(self._webdriver.window_handles[0])

        return soup

    @classmethod
    def _get_submitted_image_details(cls, tweet_soup):
        image_details = []
        images = tweet_soup.find_all(
            'img',
            class_='css-9pa8cd',
            src=re.compile('.*/media/.*')
        )

        for image in images:
            raw_url = image.get('src')
            stripped_url = raw_url[:raw_url.find('?format')]
            image_details.append({
                'url': ''.join([stripped_url, '.jpg']),
                'basename': stripped_url.rsplit('/', 1)[-1],
            })

        return image_details

    @classmethod
    def _has_video(cls, tweet_soup):
        return tweet_soup.find(
            'div',
            class_=(
                'css-1dbjc4n r-1p0dtai r-1loqt21 r-1d2f490 '
                'r-u8s1d r-zchlnj r-ipm5af'
            )
        ) is not None
