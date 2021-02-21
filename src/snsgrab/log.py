import os
import logging
import logging.handlers

from appdirs import user_log_dir

APP_NAME = 'snsgrab'

logger = None


def setup_logger(sns_name, account_name):
    def _get_logger(handlers):
        logger = logging.getLogger(APP_NAME)
        logger.setLevel(logging.INFO)

        for handler in handlers:
            logger.addHandler(handler)

        return logger

    global logger

    extra = {'accountname': account_name}

    # Avoid duplicate logging
    if logger is None:
        log_filename = '{}.log'.format(sns_name)
        log_dirpath = os.path.join(
            user_log_dir(APP_NAME),
            sns_name,
        )
        log_fullpath = os.path.join(log_dirpath, log_filename)

        os.makedirs(log_dirpath, exist_ok=True)

        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - '
            '%(accountname)s - %(message)s'
        )

        file_handler = logging.handlers.TimedRotatingFileHandler(
            filename=log_fullpath,
            when='midnight',
            interval=1,
            backupCount=0,
            encoding='UTF-8'
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)

        logger = logging.LoggerAdapter(_get_logger([file_handler]), extra)
    else:
        logger.extra = extra
