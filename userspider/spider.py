#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import codecs
import copy
import csv
import json
import math
import os
import random
import sys
import traceback
from collections import OrderedDict
from datetime import date, datetime, timedelta
from time import sleep

import requests
from lxml import etree
from requests.adapters import HTTPAdapter
from tqdm import tqdm


class Weibo(object):
    def __init__(self, config):
        self.validate_config(config)
        self.filter = config[
            'filter']  
        since_date = str(config['since_date'])
        if since_date.isdigit():
            since_date = str(date.today() - timedelta(int(since_date)))
        self.since_date = since_date 
        self.write_mode = config[
            'write_mode']  
        self.original_pic_download = config[
            'original_pic_download'] 
        self.retweet_pic_download = config[
            'retweet_pic_download'] 
        self.original_video_download = config[
            'original_video_download'] 
        self.retweet_video_download = config[
            'retweet_video_download']  
        self.cookie = {'Cookie': config.get('cookie')} 
        self.db_config = config['db_config']  
        self.print_debug = config['print_debug']
        user_id_list = config['user_id_list']
        if not isinstance(user_id_list, list):
            if not os.path.isabs(user_id_list):
                user_id_list = os.path.split(
                    os.path.realpath(__file__))[0] + os.sep + user_id_list
            self.user_config_file_path = user_id_list 
            user_config_list = self.get_user_config_list(user_id_list)
        else:
            self.user_config_file_path = ''
            user_config_list = [{
                'user_id': user_id,
                'since_date': self.since_date
            } for user_id in user_id_list]
        self.user_config_list = user_config_list
        self.user_exists = True  
        self.user_config = {}  
        self.start_date = '' 
        self.user = {}  
        self.got_count = 0  
        self.weibo = []  
        self.weibo_id_list = [] 

    def validate_config(self, config):
        """验证配置是否正确"""

        # 验证filter、original_pic_download、retweet_pic_download、original_video_download、retweet_video_download
        argument_lsit = [
            'filter', 'original_pic_download', 'retweet_pic_download',
            'original_video_download', 'retweet_video_download'
        ]
        for argument in argument_lsit:
            if config[argument] != 0 and config[argument] != 1:
                sys.exit(u'%s should be 0 or 1' % config[argument])

        # 验证since_date
        since_date = str(config['since_date'])
        if (not self.is_date(since_date)) and (not since_date.isdigit()):
            sys.exit(u'since_date should be yyyy-mm-dd or integer')

        # 验证write_mode
        write_mode = ['csv', 'json', 'mongo', 'mysql']
        if not isinstance(config['write_mode'], list):
            sys.exit(u'write_mode should be list')
        for mode in config['write_mode']:
            if mode not in write_mode:
                sys.exit(
                    u'%s non exists' %
                    mode)

        # 验证user_id_list
        user_id_list = config['user_id_list']
        if (not isinstance(user_id_list,
                           list)) and (not user_id_list.endswith('.txt')):
            sys.exit(u'user_id_list shoule be list or file path')
        if not isinstance(user_id_list, list):
            if not os.path.isabs(user_id_list):
                user_id_list = os.path.split(
                    os.path.realpath(__file__))[0] + os.sep + user_id_list
            if not os.path.isfile(user_id_list):
                sys.exit(u'%s non-exists' % user_id_list)

    def is_date(self, since_date):
        """判断日期格式是否正确"""
        try:
            datetime.strptime(since_date, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    def get_json(self, params):
        """获取网页中json数据"""
        url = 'https://m.weibo.cn/api/container/getIndex?'
        r = requests.get(url, params=params, cookies=self.cookie)
        return r.json()

    def get_weibo_json(self, page):
        """获取网页中微博json数据"""
        params = {
            'containerid': '107603' + str(self.user_config['user_id']),
            'page': page
        }
        js = self.get_json(params)
        return js

    def user_to_mongodb(self):
        """将爬取的用户信息写入MongoDB数据库"""
        user_list = [self.user]
        self.info_to_mongodb('user', user_list)
        print(u'%s inserted to database' % self.user['screen_name'])

    def user_to_mysql(self):
        """将爬取的用户信息写入MySQL数据库"""
        db_config = {
            'host': 'localhost',
            'port': 3306,
            'user': 'root',
            'password': '123456',
            'charset': 'utf8mb4'
        }
        # 创建'weibo'数据库
        create_database = """CREATE DATABASE IF NOT EXISTS weibo DEFAULT
                         CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"""
        self.mysql_create_database(db_config, create_database)
        # 创建'user'表
        create_table = """
                CREATE TABLE IF NOT EXISTS user (
                id varchar(20) NOT NULL,
                screen_name varchar(30),
                gender varchar(10),
                statuses_count INT,
                followers_count INT,
                follow_count INT,
                description varchar(140),
                profile_url varchar(200),
                profile_image_url varchar(200),
                avatar_hd varchar(200),
                urank INT,
                mbrank INT,
                verified BOOLEAN DEFAULT 0,
                verified_type INT,
                verified_reason varchar(140),
                PRIMARY KEY (id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""
        self.mysql_create_table(db_config, create_table)
        self.mysql_insert(db_config, 'user', [self.user])
        print(u'%s inserted to database' % self.user['screen_name'])

    def user_to_database(self):
        """将用户信息写入数据库"""
        if 'mysql' in self.write_mode:
            self.user_to_mysql()
        if 'mongo' in self.write_mode:
            self.user_to_mongodb()

    def get_user_info(self):
        """获取用户信息"""
        params = {'containerid': '100505' + str(self.user_config['user_id'])}
        js = self.get_json(params)
        if js['ok']:
            info = js['data']['userInfo']
            user_info = {}
            user_info['id'] = self.user_config['user_id']
            user_info['screen_name'] = info.get('screen_name', '')
            user_info['gender'] = info.get('gender', '')
            user_info['statuses_count'] = info.get('statuses_count', 0)
            user_info['followers_count'] = info.get('followers_count', 0)
            user_info['follow_count'] = info.get('follow_count', 0)
            user_info['description'] = info.get('description', '')
            user_info['profile_url'] = info.get('profile_url', '')
            user_info['profile_image_url'] = info.get('profile_image_url', '')
            user_info['avatar_hd'] = info.get('avatar_hd', '')
            user_info['urank'] = info.get('urank', 0)
            user_info['mbrank'] = info.get('mbrank', 0)
            user_info['verified'] = info.get('verified', False)
            user_info['verified_type'] = info.get('verified_type', 0)
            user_info['verified_reason'] = info.get('verified_reason', '')
            user = self.standardize_info(user_info)
            self.user = user
            self.user_to_database()
            self.user_exists = True
            return user
        else:
            print("User isn't exists >>>>>> PASS ", self.user_config['user_id'])
            self.user_exists = False
            return False

    def get_long_weibo(self, id):
        """获取长微博"""
        for i in range(5):
            url = 'https://m.weibo.cn/detail/%s' % id
            html = requests.get(url, cookies=self.cookie).text
            html = html[html.find('"status":'):]
            html = html[:html.rfind('"hotScheme"')]
            html = html[:html.rfind(',')]
            html = '{' + html + '}'
            js = json.loads(html, strict=False)
            weibo_info = js.get('status')
            if weibo_info:
                weibo = self.parse_weibo(weibo_info)
                return weibo
            sleep(random.randint(6, 10))

    def get_pics(self, weibo_info):
        """获取微博原始图片url"""
        if weibo_info.get('pics'):
            pic_info = weibo_info['pics']
            pic_list = [pic['large']['url'] for pic in pic_info]
            pics = ','.join(pic_list)
        else:
            pics = ''
        return pics

    def get_live_photo(self, weibo_info):
        """获取live photo中的视频url"""
        live_photo_list = []
        live_photo = weibo_info.get('pic_video')
        if live_photo:
            prefix = 'https://video.weibo.com/media/play?livephoto=//us.sinaimg.cn/'
            for i in live_photo.split(','):
                if len(i.split(':')) == 2:
                    url = prefix + i.split(':')[1] + '.mov'
                    live_photo_list.append(url)
            return live_photo_list

    def get_video_url(self, weibo_info):
        """获取微博视频url"""
        video_url = ''
        video_url_list = []
        if weibo_info.get('page_info'):
            if weibo_info['page_info'].get('media_info') and weibo_info[
                    'page_info'].get('type') == 'video':
                media_info = weibo_info['page_info']['media_info']
                video_url = media_info.get('mp4_720p_mp4')
                if not video_url:
                    video_url = media_info.get('mp4_hd_url')
                    if not video_url:
                        video_url = media_info.get('mp4_sd_url')
                        if not video_url:
                            video_url = media_info.get('stream_url_hd')
                            if not video_url:
                                video_url = media_info.get('stream_url')
        if video_url:
            video_url_list.append(video_url)
        live_photo_list = self.get_live_photo(weibo_info)
        if live_photo_list:
            video_url_list += live_photo_list
        return ';'.join(video_url_list)

    def download_one_file(self, url, file_path, type, weibo_id):
        """下载单个文件(图片/视频)"""
        try:
            if not os.path.isfile(file_path):
                s = requests.Session()
                s.mount(url, HTTPAdapter(max_retries=5))
                downloaded = s.get(url, cookies=self.cookie, timeout=(5, 10))
                with open(file_path, 'wb') as f:
                    f.write(downloaded.content)
        except Exception as e:
            error_file = self.get_filepath(
                type) + os.sep + 'not_downloaded.txt'
            with open(error_file, 'ab') as f:
                url = str(weibo_id) + ':' + url + '\n'
                f.write(url.encode(sys.stdout.encoding))
            print('Error: ', e)
            traceback.print_exc()

    def handle_download(self, file_type, file_dir, urls, w):
        """处理下载相关操作"""
        file_prefix = w['created_at'][:11].replace('-', '') + '_' + str(
            w['id'])
        if file_type == 'img':
            if ',' in urls:
                url_list = urls.split(',')
                for i, url in enumerate(url_list):
                    file_suffix = url[url.rfind('.'):]
                    file_name = file_prefix + '_' + str(i + 1) + file_suffix
                    file_path = file_dir + os.sep + file_name
                    self.download_one_file(url, file_path, file_type, w['id'])
            else:
                file_suffix = urls[urls.rfind('.'):]
                file_name = file_prefix + file_suffix
                file_path = file_dir + os.sep + file_name
                self.download_one_file(urls, file_path, file_type, w['id'])
        else:
            file_suffix = '.mp4'
            if ';' in urls:
                url_list = urls.split(';')
                if url_list[0].endswith('.mov'):
                    file_suffix = '.mov'
                for i, url in enumerate(url_list):
                    file_name = file_prefix + '_' + str(i + 1) + file_suffix
                    file_path = file_dir + os.sep + file_name
                    self.download_one_file(url, file_path, file_type, w['id'])
            else:
                if urls.endswith('.mov'):
                    file_suffix = '.mov'
                file_name = file_prefix + file_suffix
                file_path = file_dir + os.sep + file_name
                self.download_one_file(urls, file_path, file_type, w['id'])

    def download_files(self, file_type, weibo_type, wrote_count):
        """下载文件(图片/视频)"""
        try:
            describe = ''
            if file_type == 'img':
                describe = u'Image'
                key = 'pics'
            else:
                describe = u'Video'
                key = 'video_url'
            if weibo_type == 'original':
                describe = u'OriginalContent' + describe
            else:
                describe = u'Retweet' + describe
            print(u'Ready to download %s' % describe)
            file_dir = self.get_filepath(file_type)
            file_dir = file_dir + os.sep + describe
            if not os.path.isdir(file_dir):
                os.makedirs(file_dir)
            for w in tqdm(self.weibo[wrote_count:], desc='Download progress'):
                if weibo_type == 'retweet':
                    if w.get('retweet'):
                        w = w['retweet']
                    else:
                        continue
                if w.get(key):
                    self.handle_download(file_type, file_dir, w.get(key), w)
            print(u'%s downloaded to:' % describe)
            print(file_dir)
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_location(self, selector):
        """获取微博发布位置"""
        location_icon = 'timeline_card_small_location_default.png'
        span_list = selector.xpath('//span')
        location = ''
        for i, span in enumerate(span_list):
            if span.xpath('img/@src'):
                if location_icon in span.xpath('img/@src')[0]:
                    location = span_list[i + 1].xpath('string(.)')
                    break
        return location

    def get_topics(self, selector):
        """获取参与的微博话题"""
        span_list = selector.xpath("//span[@class='surl-text']")
        topics = ''
        topic_list = []
        for span in span_list:
            text = span.xpath('string(.)')
            if len(text) > 2 and text[0] == '#' and text[-1] == '#':
                topic_list.append(text[1:-1])
        if topic_list:
            topics = ','.join(topic_list)
        return topics

    def get_at_users(self, selector):
        """获取@用户"""
        a_list = selector.xpath('//a')
        at_users = ''
        at_list = []
        for a in a_list:
            if '@' + a.xpath('@href')[0][3:] == a.xpath('string(.)'):
                at_list.append(a.xpath('string(.)')[1:])
        if at_list:
            at_users = ','.join(at_list)
        return at_users

    def string_to_int(self, string):
        """字符串转换为整数"""
        if isinstance(string, int):
            return string
        elif string.endswith(u'万+'):
            string = int(string[:-2] + '0000')
        elif string.endswith(u'万'):
            string = int(string[:-1] + '0000')
        return int(string)

    def standardize_date(self, created_at):
        """标准化微博发布时间"""
        if u"刚刚" in created_at:
            created_at = datetime.now().strftime("%Y-%m-%d")
        elif u"分钟" in created_at:
            minute = created_at[:created_at.find(u"分钟")]
            minute = timedelta(minutes=int(minute))
            created_at = (datetime.now() - minute).strftime("%Y-%m-%d")
        elif u"小时" in created_at:
            hour = created_at[:created_at.find(u"小时")]
            hour = timedelta(hours=int(hour))
            created_at = (datetime.now() - hour).strftime("%Y-%m-%d")
        elif u"昨天" in created_at:
            day = timedelta(days=1)
            created_at = (datetime.now() - day).strftime("%Y-%m-%d")
        elif created_at.count('-') == 1:
            year = datetime.now().strftime("%Y")
            created_at = year + "-" + created_at
        return created_at

    def standardize_info(self, weibo):
        """标准化信息，去除乱码"""
        for k, v in weibo.items():
            if 'bool' not in str(type(v)) and 'int' not in str(
                    type(v)) and 'list' not in str(
                        type(v)) and 'long' not in str(type(v)):
                weibo[k] = v.replace(u"\u200b", "").encode(
                    sys.stdout.encoding, "ignore").decode(sys.stdout.encoding)
        return weibo

    def parse_weibo(self, weibo_info):
        weibo = OrderedDict()
        if weibo_info['user']:
            weibo['user_id'] = weibo_info['user']['id']
            weibo['screen_name'] = weibo_info['user']['screen_name']
        else:
            weibo['user_id'] = ''
            weibo['screen_name'] = ''
        weibo['id'] = int(weibo_info['id'])
        weibo['bid'] = weibo_info['bid']
        text_body = weibo_info['text']
        selector = etree.HTML(text_body)
        weibo['text'] = etree.HTML(text_body).xpath('string(.)')
        weibo['pics'] = self.get_pics(weibo_info)
        weibo['video_url'] = self.get_video_url(weibo_info)
        weibo['location'] = self.get_location(selector)
        weibo['created_at'] = weibo_info['created_at']
        weibo['source'] = weibo_info['source']
        weibo['attitudes_count'] = self.string_to_int(
            weibo_info.get('attitudes_count', 0))
        weibo['comments_count'] = self.string_to_int(
            weibo_info.get('comments_count', 0))
        weibo['reposts_count'] = self.string_to_int(
            weibo_info.get('reposts_count', 0))
        weibo['topics'] = self.get_topics(selector)
        weibo['at_users'] = self.get_at_users(selector)
        return self.standardize_info(weibo)

    def print_user_info(self):
        """打印用户信息"""
        print('+' * 100)
        print(u'UserInfo')
        print(u'Userid：%s' % self.user['id'])
        print(u'ScreenName：%s' % self.user['screen_name'])
        gender = u'女' if self.user['gender'] == 'f' else u'男'
        print(u'Gender：%s' % gender)
        print(u'WeiboCount：%d' % self.user['statuses_count'])
        print(u'Followers：%d' % self.user['followers_count'])
        print(u'Follow：%d' % self.user['follow_count'])
        print(u'url：https://m.weibo.cn/profile/%s' % self.user['id'])
        if self.user.get('verified_reason'):
            print(self.user['verified_reason'])
        print(self.user['description'])
        print('+' * 100)

    def print_one_weibo(self, weibo):
        """打印一条微博"""
        print(u'WeiboId：%d' % weibo['id'])
        print(u'WeiboContent：%s' % weibo['text'])
        print(u'Imageurl：%s' % weibo['pics'])
        print(u'Location：%s' % weibo['location'])
        print(u'Date：%s' % weibo['created_at'])
        print(u'Source：%s' % weibo['source'])
        print(u'Likes：%d' % weibo['attitudes_count'])
        print(u'Comments：%d' % weibo['comments_count'])
        print(u'Retweets：%d' % weibo['reposts_count'])
        print(u'Topics：%s' % weibo['topics'])
        print(u'@user：%s' % weibo['at_users'])
        print(u'url：https://m.weibo.cn/detail/%d' % weibo['id'])

    def print_weibo(self, weibo):
        """打印微博，若为转发微博，会同时打印原创和转发部分"""
        if weibo.get('retweet'):
            print('*' * 100)
            print(u'Retweet Content：')
            self.print_one_weibo(weibo['retweet'])
            print('*' * 100)
            print(u'Oringinal Content：')
        self.print_one_weibo(weibo)
        print('-' * 120)

    def get_one_weibo(self, info):
        try:
            weibo_info = info['mblog']
            weibo_id = weibo_info['id']
            retweeted_status = weibo_info.get('retweeted_status')
            is_long = weibo_info.get('isLongText')
            if retweeted_status:  # 转发
                retweet_id = retweeted_status.get('id')
                is_long_retweet = retweeted_status.get('isLongText')
                if is_long:
                    weibo = self.get_long_weibo(weibo_id)
                    if not weibo:
                        weibo = self.parse_weibo(weibo_info)
                else:
                    weibo = self.parse_weibo(weibo_info)
                if is_long_retweet:
                    retweet = self.get_long_weibo(retweet_id)
                    if not retweet:
                        retweet = self.parse_weibo(retweeted_status)
                else:
                    retweet = self.parse_weibo(retweeted_status)
                retweet['created_at'] = self.standardize_date(
                    retweeted_status['created_at'])
                weibo['retweet'] = retweet
            else:  # 原创
                if is_long:
                    weibo = self.get_long_weibo(weibo_id)
                    if not weibo:
                        weibo = self.parse_weibo(weibo_info)
                else:
                    weibo = self.parse_weibo(weibo_info)
            weibo['created_at'] = self.standardize_date(
                weibo_info['created_at'])
            return weibo
        except Exception as e:
            print("Error: ", e)
            traceback.print_exc()

    def is_pinned_weibo(self, info):
        weibo_info = info['mblog']
        title = weibo_info.get('title')
        if title and title.get('text') == u'置顶':
            return True
        else:
            return False

    def get_one_page(self, page):
        try:
            js = self.get_weibo_json(page)
            if js['ok']:
                weibos = js['data']['cards']
                for w in weibos:
                    if w['card_type'] == 9:
                        wb = self.get_one_weibo(w)
                        if wb:
                            if wb['id'] in self.weibo_id_list:
                                continue
                            created_at = datetime.strptime(
                                wb['created_at'], '%Y-%m-%d')
                            since_date = datetime.strptime(
                                self.user_config['since_date'], '%Y-%m-%d')
                            if created_at < since_date:
                                if self.is_pinned_weibo(w):
                                    continue
                                else:
                                    print(u'Already got {}({}) the {} pages'.format(self.user['screen_name'],self.user['id'], page))
                                    return True
                            if (not self.filter) or (
                                    'retweet' not in wb.keys()):
                                self.weibo.append(wb)
                                self.weibo_id_list.append(wb['id'])
                                self.got_count += 1
                                if self.print_debug == 1:
                                    self.print_weibo(wb)
            print(u'Already got {}({}) the {} pages'.format(self.user['screen_name'],self.user['id'], page))
        except Exception as e:
            print("Error: ", e)
            traceback.print_exc()

    def get_page_count(self):
        try:
            weibo_count = self.user['statuses_count']
            page_count = int(math.ceil(weibo_count / 10.0))
            return page_count
        except KeyError:
            print('user non exits')

    def get_write_info(self, wrote_count):
        write_info = []
        for w in self.weibo[wrote_count:]:
            wb = OrderedDict()
            for k, v in w.items():
                if k not in ['user_id', 'screen_name', 'retweet']:
                    if 'unicode' in str(type(v)):
                        v = v.encode('utf-8')
                    wb[k] = v
            if not self.filter:
                if w.get('retweet'):
                    wb['is_original'] = False
                    for k2, v2 in w['retweet'].items():
                        if 'unicode' in str(type(v2)):
                            v2 = v2.encode('utf-8')
                        wb['retweet_' + k2] = v2
                else:
                    wb['is_original'] = True
            write_info.append(wb)
        return write_info

    def get_filepath(self, type):
        try:
            file_dir = os.path.split(
                os.path.realpath(__file__)
            )[0] + os.sep + 'weibo-objectdata' + os.sep + self.user['screen_name']
            if type == 'img' or type == 'video':
                file_dir = file_dir + os.sep + type
            if not os.path.isdir(file_dir):
                os.makedirs(file_dir)
            if type == 'img' or type == 'video':
                return file_dir
            file_path = file_dir + os.sep + self.user_config[
                'user_id'] + '.' + type
            return file_path
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_result_headers(self):
        result_headers = [
            'id', 'bid', 'Content', 'Imageurl', 'Videourl', 'Location', 'Date', 'From', 'Likes',
            'Comments', 'Retweet', 'Topics', '@user'
        ]
        if not self.filter:
            result_headers2 = ['IfOriginal', 'SourceUserId', 'SourceUserName']
            result_headers3 = ['SourceWeibo' + r for r in result_headers]
            result_headers = result_headers + result_headers2 + result_headers3
        return result_headers

    def write_csv(self, wrote_count):
        write_info = self.get_write_info(wrote_count)
        result_headers = self.get_result_headers()
        result_data = [w.values() for w in write_info]
        if sys.version < '3':  # python2.x
            with open(self.get_filepath('csv'), 'ab') as f:
                f.write(codecs.BOM_UTF8)
                writer = csv.writer(f)
                if wrote_count == 0:
                    writer.writerows([result_headers])
                writer.writerows(result_data)
        else:  # python3.x
            with open(self.get_filepath('csv'),
                      'a',
                      encoding='utf-8-sig',
                      newline='') as f:
                writer = csv.writer(f)
                if wrote_count == 0:
                    writer.writerows([result_headers])
                writer.writerows(result_data)
        print(u'%d content inserted into csv:' % self.got_count)
        print(self.get_filepath('csv'))

    def update_json_data(self, data, weibo_info):
        data['user'] = self.user
        if data.get('weibo'):
            is_new = 1  # 待写入微博是否全部为新微博，即待写入微博与json中的数据不重复
            for old in data['weibo']:
                if weibo_info[-1]['id'] == old['id']:
                    is_new = 0
                    break
            if is_new == 0:
                for new in weibo_info:
                    flag = 1
                    for i, old in enumerate(data['weibo']):
                        if new['id'] == old['id']:
                            data['weibo'][i] = new
                            flag = 0
                            break
                    if flag:
                        data['weibo'].append(new)
            else:
                data['weibo'] += weibo_info
        else:
            data['weibo'] = weibo_info
        return data

    def write_json(self, wrote_count):
        data = {}
        path = self.get_filepath('json')
        if os.path.isfile(path):
            with codecs.open(path, 'r', encoding="utf-8") as f:
                data = json.load(f)
        weibo_info = self.weibo[wrote_count:]
        data = self.update_json_data(data, weibo_info)
        with codecs.open(path, 'w', encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        print(u'%d content inserted into json file:' % self.got_count)
        print(path)

    def info_to_mongodb(self,collection, info_list):
        try:
            import pymongo
        except ImportError:
            sys.exit(u'Pymongo REQUIRED')
        try:
            from pymongo import MongoClient

            if self.db_config:
                client = MongoClient(self.db_config)
            else:
                client = MongoClient()
            db = client['weibo']
            collection = db[collection]
            if len(self.write_mode) > 1:
                new_info_list = copy.deepcopy(info_list)
            else:
                new_info_list = info_list
            for info in new_info_list:
                if not collection.find_one({'id': info['id']}):
                    collection.insert_one(info)
                else:
                    collection.update_one({'id': info['id']}, {'$set': info})
        except pymongo.errors.ServerSelectionTimeoutError:
            sys.exit(u'MONGODB REQUIRED')

    def weibo_to_mongodb(self, wrote_count):
        self.info_to_mongodb('weibo', self.weibo[wrote_count:])
        print(u'%d content inserted into mongodb' % self.got_count)

    def mysql_create(self, connection, sql):
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql)
        finally:
            connection.close()

    def mysql_create_database(self, db_config, sql):
        try:
            import pymysql
        except ImportError:
            sys.exit(u'Pymongo REQUIRED')
        try:
            if self.db_config:
                db_config = self.db_config
            connection = pymysql.connect(**db_config)
            self.mysql_create(connection, sql)
        except pymysql.OperationalError:
            sys.exit(u'MYSQL DATABASE REQUIRED')

    def mysql_create_table(self, db_config, sql):
        import pymysql

        if self.db_config:
            db_config = self.db_config
        db_config['db'] = 'weibo'
        connection = pymysql.connect(**db_config)
        self.mysql_create(connection, sql)

    def mysql_insert(self, db_config, table, data_list):
        import pymysql

        if len(data_list) > 0:
            keys = ', '.join(data_list[0].keys())
            values = ', '.join(['%s'] * len(data_list[0]))
            if self.db_config:
                db_config = self.db_config
            db_config['db'] = 'weibo'
            connection = pymysql.connect(**db_config)
            cursor = connection.cursor()
            sql = """INSERT INTO {table}({keys}) VALUES ({values}) ON
                     DUPLICATE KEY UPDATE""".format(table=table,
                                                    keys=keys,
                                                    values=values)
            update = ','.join([
                " {key} = values({key})".format(key=key)
                for key in data_list[0]
            ])
            sql += update
            try:
                cursor.executemany(
                    sql, [tuple(data.values()) for data in data_list])
                connection.commit()
            except Exception as e:
                connection.rollback()
                print('Error: ', e)
                traceback.print_exc()
            finally:
                connection.close()

    def weibo_to_mysql(self, wrote_count):
        db_config = {
            'host': 'localhost',
            'port': 3306,
            'user': 'root',
            'password': '123456',
            'charset': 'utf8mb4'
        }
        # 创建'weibo'表
        create_table = """
                CREATE TABLE IF NOT EXISTS weibo (
                id varchar(20) NOT NULL,
                bid varchar(12) NOT NULL,
                user_id varchar(20),
                screen_name varchar(20),
                text varchar(2000),
                topics varchar(200),
                at_users varchar(200),
                pics varchar(1000),
                video_url varchar(1000),
                location varchar(100),
                created_at DATETIME,
                source varchar(30),
                attitudes_count INT,
                comments_count INT,
                reposts_count INT,
                retweet_id varchar(20),
                PRIMARY KEY (id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""
        self.mysql_create_table(db_config, create_table)
        weibo_list = []
        retweet_list = []
        if len(self.write_mode) > 1:
            info_list = copy.deepcopy(self.weibo[wrote_count:])
        else:
            info_list = self.weibo[wrote_count:]
        for w in info_list:
            if 'retweet' in w:
                w['retweet']['retweet_id'] = ''
                retweet_list.append(w['retweet'])
                w['retweet_id'] = w['retweet']['id']
                del w['retweet']
            else:
                w['retweet_id'] = ''
            weibo_list.append(w)
        # 在'weibo'表中插入或更新微博数据
        self.mysql_insert(db_config, 'weibo', retweet_list)
        self.mysql_insert(db_config, 'weibo', weibo_list)
        print(u'%d content inserted into mysql' % self.got_count)

    def update_user_config_file(self, user_config_file_path):
        print("Updating user config file")
        with open(user_config_file_path, 'rb') as f:
            try:
                lines = f.read().splitlines()
                lines = [line.decode('utf-8-sig') for line in lines]
            except UnicodeDecodeError:
                sys.exit(u'%s uft-8 format needed' %
                         user_config_file_path)
            for i, line in enumerate(lines):
                info = line.split(' ')
                if len(info) > 0 and info[0].isdigit():
                    if self.user_config['user_id'] == info[0]:
                        if self.user_exists:
                            # if user exists and user_id is verified
                            # update the line of user id
                            if len(info) == 1:
                                if self.user['screen_name']: 
                                    info.append(self.user['screen_name'])
                                else:
                                    info.append("non_screen_name")
                                info.append(self.start_date)
                            if len(info) == 2:
                                info.append(self.start_date)
                            if len(info) > 2:
                                info[2] = self.start_date
                            lines[i] = ' '.join(info)
                            break
                        else:
                            # if user is not exists or user_id is not verified
                            # remove the line of user_id
                            lines = lines[:i] + lines[i+1:]
                            break
        with codecs.open(user_config_file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

    def write_data(self, wrote_count):
        """将爬到的信息写入文件或数据库"""
        if self.got_count > wrote_count:
            if 'csv' in self.write_mode:
                self.write_csv(wrote_count)
            if 'json' in self.write_mode:
                self.write_json(wrote_count)
            if 'mysql' in self.write_mode:
                self.weibo_to_mysql(wrote_count)
            if 'mongo' in self.write_mode:
                self.weibo_to_mongodb(wrote_count)
            if self.original_pic_download:
                self.download_files('img', 'original', wrote_count)
            if self.original_video_download:
                self.download_files('video', 'original', wrote_count)
            if not self.filter:
                if self.retweet_pic_download:
                    self.download_files('img', 'retweet', wrote_count)
                if self.retweet_video_download:
                    self.download_files('video', 'retweet', wrote_count)

    def get_pages(self):
        """获取全部微博"""
        if self.get_user_info():
            page_count = self.get_page_count()
            wrote_count = 0
            if self.print_debug == 1:
                self.print_user_info()
            page1 = 0
            random_pages = random.randint(1, 5)
            self.start_date = datetime.now().strftime('%Y-%m-%d')
            for page in tqdm(range(1, page_count + 1), desc='Progress'):
                is_end = self.get_one_page(page)
                if is_end:
                    break

                if page % 20 == 0: 
                    self.write_data(wrote_count)
                    wrote_count = self.got_count

                # 通过加入随机等待避免被限制。爬虫速度过快容易被系统限制(一段时间后限
                # 制会自动解除)，加入随机等待模拟人的操作，可降低被系统限制的风险。
                if (page - page1) % random_pages == 0 and page < page_count:
                    sleep(random.randint(10, 14))
                    page1 = page
                    random_pages = random.randint(1, 5)

            self.write_data(wrote_count)  
            print(u'Spider Done，get total %d weibo content' % self.got_count)
        return False

    def get_user_config_list(self, file_path):
        """获取文件中的微博id信息"""
        with open(file_path, 'rb') as f:
            lines = f.read().splitlines()
            lines = [line.decode('utf-8-sig') for line in lines]
            user_config_list = []
            for line in lines:
                info = line.split(' ')
                if len(info) > 0 and info[0].isdigit():
                    user_config = {}
                    user_config['user_id'] = info[0]
                    if len(info) > 2 and self.is_date(info[2]):
                        user_config['since_date'] = info[2]
                        # add pass tag to skip the finished content
                        user_config['ifPass'] = True
                    else:
                        user_config['since_date'] = self.since_date
                        user_config['ifPass'] = False
                    user_config_list.append(user_config)
        return user_config_list

    def initialize_info(self, user_config):
        """初始化爬虫信息"""
        self.weibo = []
        self.user = {}
        self.user_config = user_config
        self.got_count = 0
        self.weibo_id_list = []

    def start(self):
        """运行爬虫"""
        try:
            for index, user_config in enumerate(self.user_config_list):
                if user_config['ifPass']:
                    # This will skip the user scripted before
                    continue
                if index%10 == 0:
                    print("pasue for ip checking")
                    sleep(random.randint(6, 10))
                print("spidering user", user_config['user_id'])
                self.initialize_info(user_config)
                if self.get_pages():
                    print(u'Finished this task')
                    print('*' * 100)
                if self.user_config_file_path:
                    self.update_user_config_file(self.user_config_file_path)
                else:
                    print(u'Continue next id')
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()


def main():
    try:
        config_path = os.path.split(
            os.path.realpath(__file__))[0] + os.sep + 'config.json'
        if not os.path.isfile(config_path):
            sys.exit(u'current path：%s non exists config.json' %
                     (os.path.split(os.path.realpath(__file__))[0] + os.sep))
        with open(config_path) as f:
            try:
                config = json.loads(f.read())
            except ValueError:
                sys.exit(u'config.json')
        wb = Weibo(config)

        wb.start() # start
    except Exception as e:
        print('Error: ', e)
        traceback.print_exc()


if __name__ == '__main__':
    main()