import requests  # downloading data from websites
import bs4  # beautifulsoup4, HTML parsing
from fake_useragent import UserAgent  # to spoof headers
import re  # link pattern matching, price string stripping
import numpy as np  # outlier detection
from multiprocessing.dummy import Pool  # multi-threading

ua = UserAgent()
headers = {'User-Agent': ua.random}  # headers should be in dictionary. ua.random generates a browser like UA string

item_re = re.compile(r'https://www.ebay.com/itm/.+/\d+')

html_selectors = [
                '#convbidPrice',
                '#convbinPrice',
                '#w3 > div > div.nodestar-item-card-details__table-row1 > div.nodestar-item-card-details > '
                'div.nodestar-item-card-details__content-wrapper > div.nodestar-item-card-details__condition-wrapper '
                '> div > div:nth-child(3) > div:nth-child(2) > span > span > span',
                '#prcIsum',
                '#mm-saleDscPrc',
                '#prcIsum_bidPrice']


def get_price(link):
    """Returns item price from eBay item link."""
    page = requests.get(link)
    soup = bs4.BeautifulSoup(page.text, 'lxml')
    for selector in html_selectors:  # loops through possible selectors as specified in html_selectors
        try:
            return float(re.sub('[^0-9.]', '', soup.select(selector)[0].text.strip()))
            # block is US ${price} so we take number only and convert to float, re.sub() to cut number out
        except IndexError:
            pass
    page = requests.get(link + '?nordt=true&orig_cvip=true')  # no blocks worked, try original item page
    soup = bs4.BeautifulSoup(page.text, 'lxml')
    for selector in html_selectors:
        try:
            return float(re.sub('[^0-9.]', '', soup.select(selector)[0].text.strip()))
        except IndexError:
            pass
    return -1  # returns -1 if price was not found, for later removal from price_list


def get_links(search, num_items):
    """
    Gets all eBay item page links from a search.

    Automatically adds the LH_Sold=1 and LH_Complete=1 tags to the search URL.
    """
    search_page = requests.get(f'https://www.ebay.com/sch/{search}\
    &LH_Sold=1&LH_Complete=1&_ipg={num_items}', headers=headers)  # tags for sold items
    soup = bs4.BeautifulSoup(search_page.text, 'lxml')
    link_list = []
    for link in soup.find_all('a'):
        if item_re.search(link['href']):  # if eBay item link is in href (returns non-None value) as defined by item_re
            link_list.append(item_re.search(link['href']).group())
    return list(set(link_list))


def remove_outliers(data, z_thresh=2):
    # https://medium.com/datadriveninvestor/finding-outliers-in-dataset-using-python-efc3fce6ce32
    """
    Removes outliers from list.

    Defaults to anything that falls outside of 2 standard deviations.
    """
    outliers = []
    threshold = z_thresh
    mean = np.mean(data)
    std_dev = np.std(data)

    for y in data:
        z_score = (y - mean) / std_dev
        if y < 0 or np.abs(z_score) > threshold:
            outliers.append(y)

    for elem in outliers:
        data.remove(elem)

    return len(outliers)


def ebay_avg_price(search, num_items=25):  # num_items = 25, 50, 100, 200
"""Runs program, using multiprocessing to speed up process"""
    with Pool(200) as pool:
        price_list = list(pool.map(get_price, get_links(search, num_items)))

    num_outliers = remove_outliers(price_list)
    avg_price = np.mean(price_list)

    print(
        f"The average price of the last {num_items} sales of '{search}' is\n${avg_price:.2f}"
        f" ({num_outliers} outliers removed)")


if __name__ == '__main__':
    s = input("Enter search term: ")
    ebay_avg_price(s, 100)
