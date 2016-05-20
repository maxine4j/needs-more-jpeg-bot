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

subreddits = 'Arwic'  # this can be a multireddit, i.e. sub1+sub2+sub3
white_listed_authors = []
black_listed_authors = []
triggers = [
    'needs more jpeg compression',
    'needs more jpg compression',
    'needs more jpeg',
    'needs more jpg',
    'nice jpeg compression',
    'nice jpg compression',
    'nice jpeg',
    'nice jpg',
    'need any more jpeg compression',
    'need any more jpg compression',
    'need any more jpeg',
    'need any more jpg'
]
max_pull = 100
pull_period = 60
compression_quality = 1
direct_imgur_link = 'http://i.imgur.com/'
indirect_imgur_link = 'http://imgur.com/'
imgur_url = 'imgur.com'
db_file = 'jpegbot.db'
temp_dir = '.jpegbot'
reply_template = \
'''
[Here you go](%s)

---

^(I am a bot) [^([Contact Author])](http://np.reddit.com/message/compose/?to=Arwic&amp;subject=MoreJPEGCompBot)[^([Source Code])](https://github.com/Arwic/RedditBots)
'''
debug_truncation_len = 20
imgur_download_size = 'large_thumbnail'  # ‘small_square’, ‘big_square’, ‘small_thumbnail’, ‘medium_thumbnail’, ‘large_thumbnail’, ‘huge_thumbnail’
reddit = None
imgur = None
sql = None
cur = None


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
    sql = sqlite3.connect(db_file)
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
    path = image_handle.download(path=temp_dir, overwrite=True, size=imgur_download_size)
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
        print('Parsing submission id="%s" title="%s" author="%s"' %
              (submission.id, submission.title[:debug_truncation_len], submission.author))
        # check if it is an imgur submission
        if imgur_url not in submission.url:
            print('Scan: Submission id="%s" is not supported, ignoring it' % submission.id)
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

            # check if the comment author is white listed
            if white_listed_authors != []:
                white_listed = False
                for author in white_listed_authors:
                    if author.lower() == c_author:
                        white_listed = True
                        break
                if not white_listed:
                    print('Scan: author="%s" is not white listed, ignoring comment' % c_author)
                    continue
            # check if the comment author is black listed
            if black_listed_authors != []:
                black_listed = False
                for author in black_listed_authors:
                    if author.lower() == c_author.lower():
                        black_listed = True
                        break
                if black_listed:
                    print('Scan: author="%s" is black listed, ignoring comment' % c_author)
                    continue

            # mark the comment as parsed so we don't process it again
            mark_parsed(comment.id)

            c_body = comment.body.lower()
            if any(trigger in c_body.lower() for trigger in triggers):
                reply(submission, comment)


# prepares the programs environment
def prepare_env():
    if not os.path.isdir(temp_dir):
        os.mkdir(temp_dir)


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
