import click

from . import instagram
from . import twitter


@click.group()
def cmd():
    pass


cmd.add_command(instagram.instagram)
cmd.add_command(instagram.instagram_re)
cmd.add_command(instagram.instagram_to_db)
cmd.add_command(instagram.instagram_to_db_batch)

cmd.add_command(twitter.twitter)
cmd.add_command(twitter.twitter_to_db)
