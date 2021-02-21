from setuptools import find_packages
from setuptools import setup

setup(
    name='snsgrab',
    description='SNS media downloader',
    author='Gary Sentosa',
    author_email='gary.sentosa@gmail.com',
    packages=find_packages(where='src'),
    include_package_data=True,
    package_dir={'': 'src'},
    install_requires=[
        'appdirs>=1.4.4',
        'beautifulsoup4>=4.9.1',
        'click>=7.1.2',
        'python-dateutil>=2.8.1',
        'pymongo>=3.11.0',
        'PyVirtualDisplay>=1.3.2',
        'requests>=2.24.0',
        'selenium>=3.141.0',
        'youtube-dl>=2021.2.10',
    ],
    entry_points='''
        [console_scripts]
        snsgrab=snsgrab.__main__:main
    ''',
)
