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
import json
from PIL import Image
from oauth import reddit_app_ua, reddit_app_id, reddit_app_secret, reddit_app_uri, reddit_app_refresh
from oauth import imgur_app_id, imgur_app_secret

dir_root = 'jpegbot-data'
dir_images = os.path.join(dir_root, 'images')
path_config = os.path.join(dir_root, 'config.json')
path_reply_template = os.path.join(dir_root, 'reply.txt')
path_db = os.path.join(dir_root, 'jpegbot.db')

debug_truncation_len = 50
direct_imgur_link = 'http://i.imgur.com/'
indirect_imgur_link = 'http://imgur.com/'
imgur_url = 'imgur.com'

# from config file
imgur_download_size = 'medium_thumbnail'
pull_mode = 'hot'
pull_size = None
pull_period = 5
compression_quality = 1
triggers = []
subreddits = []
black_listed_authors = []
white_listed_authors = []
black_listed_subs = []
white_listed_subs = []
reply_template = ''

# api objects
reddit = None
imgur = None
# db objects
sql = None
cur = None

# stats
images_downloaded = 0
images_compressed = 0
images_uploaded = 0
comments_replied_to = 0
total_scans = 0
comments_parsed = 0


def load_config():
    global pull_mode, pull_size, pull_period, compression_quality, \
        imgur_download_size, triggers, subreddits, black_listed_authors, \
        white_listed_authors, black_listed_subs, white_listed_subs, reply_template

    try:
        with open(path_config, 'r') as file_handle:
            config = json.load(file_handle)
        pull_mode = config['pull_mode']
        pull_size = config['pull_size']
        pull_period = config['pull_period']
        compression_quality = config['compression_quality']
        imgur_download_size = config['imgur_download_size']
        triggers = config['triggers']
        subreddits = config['subreddits']
        black_listed_authors = config['author_blacklist']
        white_listed_authors = config['author_whitelist']
        black_listed_subs = config['subreddit_blacklist']
        white_listed_subs = config['subreddit_whitelist']
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
    global sql, cur, comments_parsed
    cur.execute('INSERT INTO processed VALUES(?)', [cid])
    sql.commit()
    comments_parsed += 1


# parses an imgur url
# returns: imgur image id or None on failure
def imgur_url_to_id(url):
    if direct_imgur_link in url:
        return url[19:-4]
    elif indirect_imgur_link in url:
        return url[17:]
    else:
        print('\t\t\tImgur to ID: Bad URL: %s' % url)
        return None


# downloads an image from imgur
# returns: image path
def download_image(imgur_id):
    global imgur, images_downloaded
    print('\t\t\tDownloading image', imgur_id)
    image_handle = imgur.get_image(imgur_id)
    path = image_handle.download(path=dir_images, overwrite=True, size=imgur_download_size)
    print('\t\t\tSuccess!', path)
    images_downloaded += 1
    return path


# uploads an image to imgur
# returns: image url
def upload_image(path):
    global imgur, images_uploaded
    print('\t\t\tUploading image', path)
    uploaded_image = imgur.upload_image(path, title="NEEDS MORE JPEG COMPRESSION")
    print('\t\t\tSuccess!', uploaded_image.link)
    images_uploaded += 1
    return uploaded_image.link


# compresses an image
# returns: path to compressed image
def compress_image(img_path):
    global images_compressed
    print('\t\t\tCompressing image', img_path)
    compressed_path = os.path.splitext(img_path)[0] + '_c.jpg'
    if os.path.isfile(compressed_path):
        os.remove(compressed_path)
    image = Image.open(img_path)
    image.save(compressed_path, 'JPEG', quality=compression_quality)
    print('\t\t\tSuccess!', compressed_path)
    images_compressed += 1
    return compressed_path


# replies to a comment
def reply(submission, comment):
    def _reply():
        global comments_replied_to
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
                print('\t\t\tReply: Reply was submitted successfully')
                comments_replied_to += 1
                break
            except praw.errors.RateLimitExceeded as error:  # keep trying if we hit the rate limit
                print('\t\tRate limit exceeded! Sleeping for', error.sleep_time, 'seconds')
                time.sleep(error.sleep_time)
    
    print('\t\t\tReply: Replying to comment id="%s" author="%s", body="%s"' % 
          (comment.id, comment.author, comment.body[:debug_truncation_len]))
    _reply()
    

# removes bad characters from string
# returns: stripped string
def strip_bad_chars(bad_chars, string):
    s = string
    for bad_char in bad_chars:
        s = s.replace(bad_char, '')
    return s


# gets submissions with the given sort mode
# mode = 'hot', 'new', 'rising', 'controversial', 'top'
# returns: list of submissions from the given feed
def get_submissions(subreddit, mode, maxpull):
    if mode == 'hot':
        return subreddit.get_hot(limit=maxpull)
    if mode == 'new':
        return subreddit.get_new(limit=maxpull)
    if mode == 'rising':
        return subreddit.get_rising(limit=maxpull)
    if mode == 'controversial':
        return subreddit.get_controversial(limit=maxpull)
    if mode == 'top':
        return subreddit.get_top(limit=maxpull)


# scans the indicated subreddits for comments
def scan():
    global total_scans
    for subreddit in subreddits:
        try:
            print('Scan: Scanning subreddit: %s' % subreddit)
            sr = reddit.get_subreddit(subreddit)
            print('Scan: Retrieving %s submissions' % pull_mode)
            submissions = get_submissions(sr, pull_mode, pull_size)
        except praw.errors.InvalidSubreddit:
            print('Error: A subreddit named "%s" does not exist!' % subreddit)

        for submission in submissions:
            subreddit = submission.subreddit
            subreddit_name = subreddit.display_name.lower()
            submission_id = submission.id
            submission_title = submission.title.lower()
            submission_author = submission.author.name.lower()
            submission_url = submission.url

            # this is very slow as it has to make an api call for EACH comment
            #submission.replace_more_comments(limit=None, threshold=0)
            comments = list(submission.comments)

            # check if the subreddit is whitelisted
            if white_listed_subs != []:
                if not any(sub == subreddit_name for sub in white_listed_subs):
                    print('\tScan: subreddit="%s" is not white listed, ignoring submission' % subreddit_name)
                    continue

            # check if the subreddit is blacklisted
            if black_listed_subs != []:
                if any(sub == subreddit_name for sub in black_listed_subs):
                    print('\tScan: subreddit="%s" is black listed, ignoring submission' % subreddit_name)
                    continue

            print('\tScan: submission id="%s" sub="%s" title="%s" author="%s" comment(s)="%i"' %
                  (submission_id, subreddit_name[:debug_truncation_len],
                   submission_title[:debug_truncation_len], submission_author[:debug_truncation_len], len(comments)))

            # check if it is an imgur submission
            if imgur_url not in submission_url:
                #print('Scan: Submission id="%s" is not supported, ignoring it' % sub_id)
                continue

            for comment in submission.comments:                
                # check if we have already parsed this comment
                comment_id = comment.id
                if has_parsed(comment_id):
                    #print('\t\tScan: Comment id="%s" has already been parsed, ignoring it' % comment_id)
                    continue

                # mark the comment as parsed so we don't process it again
                mark_parsed(comment_id)
                
                # check if the author still exists
                try:
                    comment_author = comment.author.name.lower()
                    comment_body = strip_bad_chars('\n\t', comment.body.lower())
                    print('\t\tScan: Parsing comment id="%s" author="%s", body="%s"' %
                          (comment_id, comment_author, comment_body[:debug_truncation_len]))
                except AttributeError:
                    #print('\t\tScan: Comment id="%s" has been deleted or removed, ignoring it' % comment_id)
                    continue

                # check if the comment author is whitelisted
                if white_listed_authors != []:
                    if not any(author.lower() == comment_author for author in white_listed_authors):
                        #print('\t\tScan: author="%s" is not white listed, ignoring comment' % c_author)
                        continue

                # check if the comment author is blacklisted
                if black_listed_authors != []:
                    if any(author.lower() == comment_author for author in black_listed_authors):
                        #print('\t\tScan: author="%s" is black listed, ignoring comment' % c_author)
                        continue

                if any(trigger in comment_body for trigger in triggers):
                    reply(submission, comment)
    total_scans += 1


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
    auth_db()
    while True:
        try:
            scan()
            # print stats
            print('Stats: Images downloaded =', images_downloaded)
            print('Stats: Images compressed =', images_compressed)
            print('Stats: Images uploaded =', images_uploaded)
            print('Stats: Comments parsed =', comments_parsed)
            print('Stats: Comments replied to =', comments_replied_to)
            print('Stats: Total scans =', total_scans)
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
