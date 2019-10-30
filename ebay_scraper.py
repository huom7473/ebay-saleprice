import requests  # downloading data from websites
import bs4  # beautifulsoup4, HTML parsing
from fake_useragent import UserAgent  # to spoof headers
import re  # link pattern matching, price string stripping
import numpy as np  # outlier detection
import logging  # debugging
from multiprocessing.dummy import Pool  # multi-threading
from tqdm import tqdm  # progress bar

ua = UserAgent()
headers = {'User-Agent': 'Mozilla/5.0 (Windows; U; Windows NT 5.1; ja-JP) AppleWebKit/533.20.25 (KHTML, like Gecko) '
                         'Version/5.0.3 Safari/533.19.4'}
logging.basicConfig(filename='debug_log.txt', filemode='w', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - '
                                                                                        '%(message)s')

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
    for selector in html_selectors:
        try:
            return float(re.sub('[^0-9.]', '', soup.select(selector)[0].text.strip()))
        except IndexError:
            pass
        except ValueError:  # foreign currency prices + re.sub() results in a price string like "29.0022.02"
            return float(re.sub('[^0-9.]', '', soup.select(selector)[0].text.strip().partition('.')[2][2:]))
    page = requests.get(link + '?nordt=true&orig_cvip=true')  # no blocks worked, try original item page
    soup = bs4.BeautifulSoup(page.text, 'lxml')
    for selector in html_selectors:
        try:
            return float(re.sub('[^0-9.]', '', soup.select(selector)[0].text.strip()))
        except IndexError:
            pass
        except ValueError:
            return float(re.sub('[^0-9.]', '', soup.select(selector)[0].text.strip().partition('.')[2][2:]))
    return -1  # returns -1 if price could not be found


def get_links(search, num_items):
    """
    Gets all eBay item page links from a search.

    Automatically adds the LH_Sold=1 and LH_Complete=1 tags to the search URL.
    """
    search_page = requests.get(f'https://www.ebay.com/sch/{search}    &LH_Sold=1&LH_Complete=1&_ipg={num_items}',
                               headers=headers)  # tags for sold items
    soup = bs4.BeautifulSoup(search_page.text, 'lxml')
    link_list = []
    for link in soup.find_all('a'):
        if item_re.search(link['href']):  # if eBay item link is in href (returns non-None value)as defined by item_re
            link_list.append(item_re.search(link['href']).group())
    return list(set(link_list))


def clean_prices(data, exp_price, exp_price_thresh,
                 z_thresh=2):
    # https://medium.com/datadriveninvestor/finding-outliers-in-dataset-using-python-efc3fce6ce32
    """
    Removes outliers from list.

    Defaults to anything that falls outside of 2 standard deviations. Returns # of outliers, # of fails as a tuple
    """
    thresh_fails = []
    fails = 0

    while -1 in data:  # remove failed price matches
        data.remove(-1)
        fails += 1

    if exp_price:  # if expected price is specified
        thresh_fails = [x for x in data if np.abs(x - exp_price) > exp_price * exp_price_thresh]

    for elem in thresh_fails:
        data.remove(elem)

    logging.debug(f'data used to calculate std_dev: {data}')
    mean = np.mean(data)  # calculate mean and std_dev after -1's and thresh fails are removed
    std_dev = np.std(data)

    logging.debug(f'using z_thresh {z_thresh}, std_dev {std_dev}, mean {mean}')
    outliers = [x for x in data if np.abs((x - mean) / std_dev) > z_thresh]

    for elem in outliers:
        data.remove(elem)

    logging.debug(f'thresh_fails: {thresh_fails}')
    logging.debug(f'outliers: {outliers}')

    return len(outliers), fails, len(thresh_fails)


def debug(search, num_items):
    """Prints link and attempts to get price. Use to find the link where get_price throws an error."""
    for link in get_links(search, num_items):  # debug
        print(link)
        if get_price(link) > 0:
            pass
        else:
            break


def ebay_avg_price(search, num_items=100, exp_price=None, exp_price_thresh=0.25, outlier_thresh=2):
    # num_items = 25, 50, 100, 200
    """
    Returns average price of recent sales, given a search term.

    Parameters
    ----------

    search : string
            String specifying search term to use.
    num_items : 25, 50, 100, or 200
            Specifies number of items to use in the eBay search URL.
            Will grab up to specified amount based on sales volume.
    exp_price : int, float, or None
            Option to specify an expected price. Prices that deviate
            by more than exp_price_thresh will not be considered.
    exp_price_thresh : float
            If exp_price is defined, specifies range that price must
            be in to be considered. For example, given exp_price = 100
            and exp_price_thresh = 0.2, a price must be within
            100 * 0.2 = $20 of the exp_price to be considered.
    outlier_thresh: int, float
            The number of standard deviations apart from the mean required
            to consider a price an outlier.
    """
    price_list = []
    print('Grabbing items...')
    link_list = get_links(search, num_items)
    print(f'Done - {len(link_list)} items found.\n')
    with Pool(200) as pool:
        print('Grabbing prices...')
        for price in tqdm(pool.imap_unordered(get_price, link_list), total=len(link_list)):
            price_list.append(price)
    logging.debug(f'pre-clean price_list: {price_list}')

    num_outliers, fails, thresh_fails = clean_prices(price_list, exp_price, exp_price_thresh, outlier_thresh)
    logging.debug(f'post-clean price_list: {price_list}')

    if len(price_list):  # if price list length isn't 0
        print(f"The average price of the last {num_items} sales of '{search}' is\n${np.mean(price_list):.2f}"
              f" ({num_outliers} outliers removed, {fails} failed to get price, {thresh_fails} too far from expected "
              f"price)\n"
              f"25th percentile: {np.percentile(price_list, 25)} | 75th percentile: {np.percentile(price_list, 75)} | "
              f"Std. Dev: {np.std(price_list)}\n"
              f"min: {min(price_list)} | max: {max(price_list)} | med: {np.median(price_list)}")
    else:
        print('Price list is empty. Try using different expected price values, or try a new search term.')


if __name__ == "__main__":
    search = input("Enter search string: ")
    ebay_avg_price(search, exp_price=None, exp_price_thresh=0.4, outlier_thresh=2)
