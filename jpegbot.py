"""
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

Author: Reddit: /u/Arwic
        GitHub: https://github.com/Arwic
"""

import traceback
import praw
import time
import os
import pyimgur
import json
import atexit
import re
import threading
from PIL import Image
from websocket import create_connection
from oauth import reddit_app_ua, reddit_app_id, reddit_app_secret, reddit_app_uri, reddit_app_refresh
from oauth import imgur_app_id, imgur_app_secret

dir_root = 'jpegbot-data'
dir_images = os.path.join(dir_root, 'images')
path_config = os.path.join(dir_root, 'config.json')
path_reply_template = os.path.join(dir_root, 'reply.txt')
pid_file = '/tmp/jpegbot.pid'

debug_truncation_len = 50
# from config file
imgur_download_size = 'medium_thumbnail'
compression_quality = 1
triggers = []
subreddits = []
black_listed_authors = []
white_listed_authors = []
black_listed_subs = []
reply_template = ''
rockets_subscription = ''
username = ''

# api objects
reddit = None
imgur = None
rockets_ws = None
# db objects
sql = None
cur = None

# stats
images_downloaded = 0
images_compressed = 0
images_uploaded = 0
comments_replied_to = 0
comments_parsed = 0

re_imgur = re.compile(r'imgur.com/(.{7})')


def load_config():
    global username, rockets_subscription, compression_quality, imgur_download_size, triggers, \
        subreddits, black_listed_authors, white_listed_authors, black_listed_subs, reply_template

    try:
        with open(path_config, 'r') as file_handle:
            config = json.load(file_handle)
        username = config['username'].lower()
        compression_quality = config['compression_quality']
        imgur_download_size = config['imgur_download_size']
        triggers = config['triggers']
        subreddits = config['subreddits']
        black_listed_authors = config['author_blacklist']
        white_listed_authors = config['author_whitelist']
        black_listed_subs = config['subreddit_blacklist']
    except Exception as e:
        print('Error: Bad config file: %s' % path_config)
        print(e)
        exit(1)

    try:
        with open(path_reply_template, 'r') as file_handle:
            reply_template = file_handle.read()[:-1]  # remove new line character
        if '%s' not in reply_template:
            print('Error: The reply template must contain a single "%s" where the image link will go')
            exit(1)
        if reply_template is '':
            print('Error: Empty reply template. Add one to this file: %s' % path_reply_template)
            exit(1)
    except:
        print('Error: Bad reply template file: %s' % path_reply_template)
        exit(1)

    # build the rockets request
    req = {}
    req['channel'] = 'comments'
    req['include'] = {}
    req['include']['contains'] = triggers
    req['include']['author'] = white_listed_authors
    if 'all' in subreddits:
        req['include']['subreddit'] = []
    elif subreddits == []:
        print('Error: No subreddits specified')
        exit(1)
    else:
        req['include']['subreddit'] = subreddits

    req['exclude'] = {}
    req['exclude']['author'] = black_listed_authors
    req['exclude']['subreddit'] = black_listed_subs

    rockets_subscription = json.dumps(req)


# connects to reddit with praw
def auth_reddit():
    global reddit
    print('Attempting to authenticate with reddit...')
    reddit = praw.Reddit(reddit_app_ua)
    reddit.set_oauth_app_info(reddit_app_id, reddit_app_secret, reddit_app_uri)
    reddit.refresh_access_information(reddit_app_refresh)
    print('Success')


# connects to imgur with pyimgur
def auth_imgur():
    global imgur
    print('Attempting to authenticate with imgur...')
    imgur = pyimgur.Imgur(imgur_app_id, imgur_app_secret)
    print('Success!')


def auth_rockets():
    global rockets_ws
    print('Attempting to connect to rockets...')
    rockets_ws = create_connection("ws://rockets.cc:3210")
    rockets_ws.send(rockets_subscription)
    print('Success!')


# downloads an image from imgur
# returns: image path
def download_image(imgur_id):
    global imgur, images_downloaded
    print('\t\tDownloading image', imgur_id)
    image_handle = imgur.get_image(imgur_id)
    path = image_handle.download(path=dir_images, overwrite=True, size=imgur_download_size)
    print('\t\tSuccess!', path)
    images_downloaded += 1
    return path


# uploads an image to imgur
# returns: image url
def upload_image(path):
    global imgur, images_uploaded
    print('\t\tUploading image', path)
    uploaded_image = imgur.upload_image(path, title="NEEDS MORE JPEG COMPRESSION")
    print('\t\tSuccess!', uploaded_image.link)
    images_uploaded += 1
    return uploaded_image.link


# compresses an image
# returns: path to compressed image
def compress_image(img_path):
    global images_compressed
    print('\t\tCompressing image', img_path)
    compressed_path = os.path.splitext(img_path)[0] + '_c.jpg'
    if os.path.isfile(compressed_path):
        os.remove(compressed_path)
    image = Image.open(img_path)
    image.save(compressed_path, 'JPEG', quality=compression_quality)
    print('\t\tSuccess!', compressed_path)
    images_compressed += 1
    return compressed_path


def process_image(imgur_id):
    image_path = download_image(imgur_id)  # download,
    compressed_image_path = compress_image(image_path)  # compress
    return upload_image(compressed_image_path)  # and upload the compressed image


def reply(comment_tid, imgur_id):
    def _reply():
        global comments_replied_to
        while True:
            try:
                comment = reddit.get_info(thing_id=comment_tid)
                img_link = process_image(imgur_id)
                comment.reply(reply_template % img_link)
                print('\tReply: Reply was submitted successfully')
                comments_replied_to += 1
                break
            except praw.errors.RateLimitExceeded as error:  # keep trying if we hit the rate limit
                print('\tRate limit exceeded! Sleeping for', error.sleep_time, 'seconds')
                time.sleep(error.sleep_time)
    threading.Thread(target=_reply).start()


def parse_comment():
    # get the next comment from rockets
    response = rockets_ws.recv()
    comment = json.loads(response)['data']

    print('Parse: Parsing comment id="%s" subreddit="%s" author="%s" body="%s"' %
          (comment['id'], comment['subreddit'][:debug_truncation_len],
           comment['author'][:debug_truncation_len], comment['body'][:debug_truncation_len]))

    global comments_parsed
    comments_parsed += 1

    # These checks should be covered by rockets, but it doesn't seem to work 100% of the time
    # check if the comment has a trigger in it
    if not any(trigger in comment['body'] for trigger in triggers):
        print('\tParse: Rockets Failed: No trigger in comment body, ignoring')
    # check if the subreddit is blacklisted
    sr_name = comment['subreddit']
    if black_listed_subs != []:
        if any(sub.lower() == sr_name.lower() for sub in black_listed_subs):
            print('\tParse: Rockets Failed: blacklisted subreddit "%s, ignoring"' % sr_name)
            return
    # check if the comment author is whitelisted
    c_author = comment['author']
    if white_listed_authors != []:
        if not any(author.lower() == c_author.lower() for author in white_listed_authors):
            print('\tParse: Rockets Failed: author not whitelisted "%s, ignoring"' % c_author)
            return
    # check if the comment author is blacklisted
    if black_listed_authors != []:
        if any(author.lower() == c_author.lower() for author in black_listed_authors):
            print('\tParse: Rockets Failed: blacklisted author "%s, ignoring"' % c_author)
            return

    # get comment's parent
    parent_id = comment['parent_id']
    parent = reddit.get_info(thing_id=parent_id)

    # don't reply to the bot
    if parent.author.name.lower() == username:
        print('\tParse: Image was posted by the bot, ignoring')
        return

    # get the imgur id from the parent
    if parent_id[:3] == 't1_':  # parent is a comment
        print('\tParse: Parent is a comment')
        parent_body = parent.body
    elif parent_id[:3] == 't3_':  # parent is a submission
        print('\tParse: Parent is a submission')
        parent_body = parent.url
    else:
        print('\tParse: Unsupported parent type "%s", ignoring' % parent_id[:3])
        return
    matches = re_imgur.findall(parent_body)
    if matches == []:
        print('\tParse: No imgur url found in parent, ignoring')
        return
    imgur_id = matches[0]
    print('\tParse: Found imgur url in parent, imgur_id="%s"' % imgur_id)

    # reply to the comment
    reply(comment['name'], imgur_id)


# prepares the programs environment
def prepare_env():
    if not os.path.isdir(dir_root):
        os.mkdir(dir_root)
    if not os.path.isdir(dir_images):
        os.mkdir(dir_images)


# checks to see if an instance of jpegbot is already running
def check_pidfile():
    pid = str(os.getpid())
    if os.path.isfile(pid_file):
        print('%s already exists, exiting' % pid_file)
        exit(1)
    with open(pid_file, 'w') as file_handle:
        file_handle.write(pid)


# on exit
def on_exit():
    os.remove(pid_file)


# main
def main():
    check_pidfile()
    atexit.register(on_exit)

    global compression_quality, sql

    prepare_env()

    load_config()

    auth_reddit()
    auth_imgur()
    auth_rockets()

    while True:
        try:
            parse_comment()
        except KeyboardInterrupt:
            # close web socket
            rockets_ws.close()
            # print stats
            print('Stats: Images downloaded =', images_downloaded)
            print('Stats: Images compressed =', images_compressed)
            print('Stats: Images uploaded =', images_uploaded)
            print('Stats: Comments parsed =', comments_parsed)
            print('Stats: Comments replied to =', comments_replied_to)
            break
        except:  # don't crash if there was an error
            traceback.print_exc()


if __name__ == '__main__':
    main()
