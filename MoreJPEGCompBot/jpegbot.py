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
import sqlite3
import os
import pyimgur
import optparse
from PIL import Image
from oauth import reddit_app_ua, reddit_app_id, reddit_app_secret, reddit_app_uri, reddit_app_refresh
from oauth import imgur_app_id, imgur_app_secret

dir_root = '.jpegbot'
dir_images = os.path.join(dir_root, 'images')
path_triggers = os.path.join(dir_root, 'triggers.txt')
path_subs = os.path.join(dir_root, 'subreddits.txt')
path_whitelist_author = os.path.join(dir_root, 'author_whitelist.txt')
path_blacklist_author = os.path.join(dir_root, 'author_blacklist.txt')
path_whitelist_sub = os.path.join(dir_root, 'subreddit_whitelist.txt')
path_blacklist_sub = os.path.join(dir_root, 'subreddit_blacklist.txt')
path_reply_template = os.path.join(dir_root, 'reply_template.txt')
path_db = os.path.join(dir_root, 'jpegbot.db')

subreddits = ''
reply_template = ''
white_listed_authors = []
black_listed_authors = []
white_listed_subs = []
black_listed_subs = []
triggers = []

imgur_download_size = 'medium_thumbnail'  # ‘small_square’, ‘big_square’, ‘small_thumbnail’, ‘medium_thumbnail’, ‘large_thumbnail’, ‘huge_thumbnail’
max_pull = 100
pull_period = 120
compression_quality = 1
debug_truncation_len = 20
direct_imgur_link = 'http://i.imgur.com/'
indirect_imgur_link = 'http://imgur.com/'
imgur_url = 'imgur.com'

reddit = None
imgur = None
sql = None
cur = None


def load_data():
    global subreddits, white_listed_authors, black_listed_authors, \
        white_listed_subs, black_listed_subs, triggers, reply_template

    global path_triggers, path_subs, path_whitelist_author, \
        path_blacklist_author, path_whitelist_sub, \
        path_blacklist_sub, path_reply_template

    try:
        with open(path_triggers, 'r') as file_handle:
            for line in file_handle.readlines():
                triggers.append(line[:-1].lower())  # remove new line character
        if triggers is []:
            print('Error: There are no triggers to watch for. Add some to this file: %s' % path_triggers)
            exit(1)
    except:
        print('Error: Bad trigger file: %s' % path_triggers)
        exit(1)

    try:
        with open(path_subs, 'r') as file_handle:
            for line in file_handle.readlines():
                subreddits += '+%s' % line[:-1].lower()  # remove new line character
            subreddits = subreddits[1:]  # remove the first '+'
        if subreddits is '':
            print('Error: There are no subreddits to scan. Add some to this file: %s' % path_subs)
            exit(1)
    except:
        print('Error: Bad subreddit file: %s' % path_subs)
        exit(1)

    try:
        with open(path_whitelist_author, 'r') as file_handle:
            for line in file_handle.readlines():
                white_listed_authors.append(line[:-1].lower())  # remove new line character
    except:
        print('Error: Bad author whitelist file: %s' % path_whitelist_author)
        exit(1)

    try:
        with open(path_blacklist_author, 'r') as file_handle:
            for line in file_handle.readlines():
                black_listed_authors.append(line[:-1].lower())  # remove new line character
    except:
        print('Error: Bad author blacklist file: %s' % path_blacklist_author)
        exit(1)

    try:
        with open(path_whitelist_sub, 'r') as file_handle:
            for line in file_handle.readlines():
                white_listed_subs.append(line[:-1].lower())  # remove new line character
    except:
        print('Error: Bad subreddit whitelist file: %s' % path_whitelist_sub)
        exit(1)

    try:
        with open(path_blacklist_sub, 'r') as file_handle:
            for line in file_handle.readlines():
                black_listed_subs.append(line[:-1].lower())  # remove new line character
    except:
        print('Error: Bad subreddit blacklist file: %s' % path_blacklist_sub)
        exit(1)

    try:
        with open(path_reply_template, 'r') as file_handle:
            reply_template = file_handle.read()[:-1]  # remove new line character
        if '%s' not in reply_template:
            print('Error: The reply template must contain a single "%s" where the image link will go')
            exit(1)
        if reply_template is '':
            print('Error: There isn\'t a reply template. Add one to this file: %s' % path_subs)
            exit(1)
    except:
        print('Error: Bad reply template file: %s' % path_reply_template)
        exit(1)


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


# connects to the sqlite db
def auth_db():
    global sql, cur
    print('Attempting to connect to database...')
    sql = sqlite3.connect(path_db)
    cur = sql.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS processed(ID TEXT)')
    sql.commit()
    print('Success!')


# checks whether a comment has been parsed
# returns: parsed
def has_parsed(cid):
    global sql, cur
    cur.execute('SELECT * FROM processed WHERE ID=?', [cid])
    if cur.fetchone():
        return True
    return False


# marks a comment as parsed to we can ignore it next check
def mark_parsed(cid):
    global sql, cur
    cur.execute('INSERT INTO processed VALUES(?)', [cid])
    sql.commit()


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
    global imgur
    print('Downloading image', imgur_id)
    image_handle = imgur.get_image(imgur_id)
    path = image_handle.download(path=dir_images, overwrite=True, size=imgur_download_size)
    print('Success!', path)
    return path


# uploads an image to imgur
# returns: image url
def upload_image(path):
    global imgur
    print('Uploading image', path)
    uploaded_image = imgur.upload_image(path, title="NEEDS MORE JPEG COMPRESSION")
    print('Success!', uploaded_image.link)
    return uploaded_image.link


# compresses an image
# returns: path to compressed image
def compress_image(img_path):
    print('Compressing image', img_path)
    compressed_path = os.path.splitext(img_path)[0] + '_c.jpg'
    if os.path.isfile(compressed_path):
        os.remove(compressed_path)
    image = Image.open(img_path)
    image.save(compressed_path, 'JPEG', quality=compression_quality)
    print('Success!', compressed_path)
    return compressed_path


# replies to a comment
def reply(submission, comment):
    print('Reply: Replying to comment id="%s" author="%s", body="%s"' % (comment.id, comment.author,
                                                                         comment.body[:debug_truncation_len]))
    while True:
        # get the image's id
        imgur_id = imgur_url_to_id(submission.url)
        if imgur_id is None:
            break
        image_path = download_image(imgur_id)  # download,
        compressed_image_path = compress_image(image_path)  # compress
        uploaded_image_link = upload_image(compressed_image_path)  # and reupload the image
        try:
            comment.reply(reply_template % uploaded_image_link)  # reply to the comment
            print('Reply: Reply was submitted successfully')
            break
        except praw.errors.RateLimitExceeded as error:  # keep trying if we hit the rate limit
            print('Rate limit exceeded! Sleeping for', error.sleep_time, 'seconds')
            time.sleep(error.sleep_time)


# scans the indicated subreddits for comments
def scan():
    print('Scanning subreddits: %s' % subreddits)
    sr = reddit.get_subreddit(subreddits)
    submissions = sr.get_new(limit=max_pull)
    for submission in submissions:
        sub_name = submission.subreddit.display_name.lower()
        # check if the subreddit is whitelisted
        if white_listed_subs is []:
            if not any(sub == sub_name for sub in white_listed_subs):
                print('Scan: subreddit="%s" is not white listed, ignoring submission' % sub_name)
                continue

        # check if the subreddit is blacklisted
        if black_listed_subs is []:
            if any(sub == sub_name for sub in black_listed_subs):
                print('Scan: subreddit="%s" is black listed, ignoring submission' % sub_name)
                continue

        print('Scanning: submission id="%s" sub="%s" title="%s" author="%s"' %
              (submission.id, submission.subreddit.display_name[:debug_truncation_len],
               submission.title[:debug_truncation_len], submission.author.name[:debug_truncation_len]))
        # check if it is an imgur submission
        if imgur_url not in submission.url:
            # print('Scan: Submission id="%s" is not supported, ignoring it' % submission.id)
            continue
        for comment in submission.comments:
            # check if the author still exists
            try:
                c_author = comment.author.name.lower()
                print('Scan: Parsing comment id="%s" author="%s", body="%s"' %
                      (comment.id, comment.author, comment.body[:debug_truncation_len]))
            except AttributeError:
                print('Scan: Comment id="%s" has been deleted or removed, ignoring it' % comment.id)
                continue

            # check if we have already parsed this comment
            if has_parsed(comment.id):
                print('Scan: Comment id="%s" has already been parsed, ignoring it' % comment.id)
                continue

            # mark the comment as parsed so we don't process it again
            mark_parsed(comment.id)

            # check if the comment author is whitelisted
            if white_listed_authors is []:
                if not any(author.lower() == c_author for author in white_listed_authors):
                    print('Scan: author="%s" is not white listed, ignoring comment' % c_author)
                    continue

            # check if the comment author is blacklisted
            if black_listed_authors is []:
                if any(author.lower() == c_author for author in black_listed_authors):
                    print('Scan: author="%s" is black listed, ignoring comment' % c_author)
                    continue

            c_body = comment.body.lower()
            if any(trigger in c_body.lower() for trigger in triggers):
                reply(submission, comment)


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
    load_data()

    auth_reddit()
    auth_imgur()
    auth_db()
    while True:
        try:
            scan()
        except KeyboardInterrupt:
            break
        except:  # don't crash if there was an error
            traceback.print_exc()
        print('Running again in', pull_period, 'seconds')
        time.sleep(pull_period)

    # close db
    sql.commit()
    sql.close()


if __name__ == '__main__':
    main()
