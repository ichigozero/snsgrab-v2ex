import datetime
import os
import pickle

from appdirs import user_data_dir

APP_NAME = 'snsgrab'


def export_collection_of_post_details(
        post_details,
        sns_name,
        real_name,
        logger
):
    has_content = False

    for content in post_details.values():
        if content:
            has_content = True
            break

    if has_content:
        pickle_path = get_pickle_path(
            sns_name=sns_name,
            real_name=real_name
        )

        logger.info('Exporting post details to %s', pickle_path)

        with open(pickle_path, 'wb') as f:
            pickle.dump(post_details, f)
    else:
        logger.info('No post details to export')


def get_pickle_path(sns_name, real_name):
    dirpath = os.path.join(
        user_data_dir(APP_NAME),
        sns_name,
        real_name,
    )
    os.makedirs(dirpath, exist_ok=True)

    timestamp_now = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    filename = '{}_{}.pkl'.format(real_name, timestamp_now)

    return os.path.join(dirpath, filename)
