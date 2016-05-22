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
import optparse
import json
from PIL import Image
from websocket import create_connection
from oauth import reddit_app_ua, reddit_app_id, reddit_app_secret, reddit_app_uri, reddit_app_refresh
from oauth import imgur_app_id, imgur_app_secret

dir_root = 'jpegbot-data'
dir_images = os.path.join(dir_root, 'images')
path_config = os.path.join(dir_root, 'config.json')
path_reply_template = os.path.join(dir_root, 'reply.txt')
path_log = os.path.join(dir_root, 'log.txt')

debug_truncation_len = 50
direct_imgur_link = 'http://i.imgur.com/'
indirect_imgur_link = 'http://imgur.com/'
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


def load_config():
    global rockets_subscription, compression_quality, imgur_download_size, triggers, \
        subreddits, black_listed_authors, white_listed_authors, black_listed_subs, reply_template

    try:
        with open(path_config, 'r') as file_handle:
            config = json.load(file_handle)
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
    elif len(subreddits) == 0:
        print('Error: No subreddits specified')
        exit(1)
    else:
        req['include']['subreddit'] = subreddits

    req['exclude'] = {}
    req['exclude']['author'] = black_listed_authors
    req['exclude']['subreddit'] = black_listed_subs

    req['root'] = True
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


# parses an imgur url
# returns: imgur image id or None on failure
def imgur_url_to_id(url):
    if direct_imgur_link in url:
        return url[19:-4]
    elif indirect_imgur_link in url:
        return url[17:]
    else:
        print('Imgur to ID: Bad URL: %s' % url)
        return None


# downloads an image from imgur
# returns: image path
def download_image(imgur_id):
    global imgur, images_downloaded
    print('Downloading image', imgur_id)
    image_handle = imgur.get_image(imgur_id)
    path = image_handle.download(path=dir_images, overwrite=True, size=imgur_download_size)
    print('Success!', path)
    images_downloaded += 1
    return path


# uploads an image to imgur
# returns: image url
def upload_image(path):
    global imgur, images_uploaded
    print('Uploading image', path)
    uploaded_image = imgur.upload_image(path, title="NEEDS MORE JPEG COMPRESSION")
    print('Success!', uploaded_image.link)
    images_uploaded += 1
    return uploaded_image.link


# compresses an image
# returns: path to compressed image
def compress_image(img_path):
    global images_compressed
    print('Compressing image', img_path)
    compressed_path = os.path.splitext(img_path)[0] + '_c.jpg'
    if os.path.isfile(compressed_path):
        os.remove(compressed_path)
    image = Image.open(img_path)
    image.save(compressed_path, 'JPEG', quality=compression_quality)
    print('Success!', compressed_path)
    images_compressed += 1
    return compressed_path


# replies to a comment
def reply(link_url, c_name):
    def _reply():
        global comments_replied_to
        while True:
            # get the image's id
            imgur_id = imgur_url_to_id(link_url)
            if imgur_id is None:
                break
            image_path = download_image(imgur_id)  # download,
            compressed_image_path = compress_image(image_path)  # compress
            uploaded_image_link = upload_image(compressed_image_path)  # and reupload the image
            try:
                comment = reddit.get_info(thing_id=c_name)
                comment.reply(reply_template % uploaded_image_link)
                print('Reply: Reply was submitted successfully')
                comments_replied_to += 1
                break
            except praw.errors.RateLimitExceeded as error:  # keep trying if we hit the rate limit
                print('Rate limit exceeded! Sleeping for', error.sleep_time, 'seconds')
                time.sleep(error.sleep_time)
    
    print('Reply: Replying to comment c_name="%s"' % c_name)
    _reply()


def parse_next_comment():
    response = rockets_ws.recv()
    comment = json.loads(response)['data']
    print(comment)

    c_link = comment['link_url']
    # check if the submission url is imgur
    if not imgur.is_imgur_url(c_link):
        return

    reply(c_link, comment['name'])


# prepares the programs environment
def prepare_env():
    if not os.path.isdir(dir_root):
        os.mkdir(dir_root)
    if not os.path.isdir(dir_images):
        os.mkdir(dir_images)


# main
def main():
    global compression_quality, sql
    parser = optparse.OptionParser()
    parser.add_option('-q', '--quality', dest='quality',
                      help='sets the quality of compression',
                      default=compression_quality,
                      nargs=1)

    options, arguments = parser.parse_args()

    try:
        compression_quality = int(options.quality)
    except TypeError:
        print('Invalid compression quality')
        exit(1)

    prepare_env()
    load_config()

    auth_reddit()
    auth_imgur()
    auth_rockets()

    while True:
        try:
            parse_next_comment()
        except KeyboardInterrupt:
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
