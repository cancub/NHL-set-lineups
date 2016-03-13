#! /usr/bin/env python2.7
import requests, re, time, smtplib, sys, datetime
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.wait import WebDriverWait
from pyvirtualdisplay import Display
import email.message
from bs4 import BeautifulSoup
import config


def main(num_days):


    display = Display(visible=0, size=(800, 600))
    display.start()

    # login to allow modification of roster
    driver = webdriver.Firefox()
    driver.get("https://login.yahoo.com")
    print driver.title
    logintxt = driver.find_element_by_name("username")
    logintxt.send_keys(config.CONFIG["login_info"]["user"])
    button = driver.find_element_by_id("login-signin")
    button.click()
    print "sending username"
    time.sleep(1)
    pwdtxt = driver.find_element_by_name("passwd")
    pwdtxt.send_keys(config.CONFIG["login_info"]["pw"])
    button = driver.find_element_by_id("login-signin")
    print "sending password"
    button.click()
    # give it time to log in
    # url = driver.current_url.encode('ascii','ignore')
    # print type(url)
    # print re.split('/',url)
    wait = WebDriverWait(driver, 10)
    wait.until(lambda driver: (re.split('/',driver.current_url.encode('ascii','ignore'))[2] \
        == "www.yahoo.com") or \
        re.split('/',driver.current_url.encode('ascii','ignore'))[2] == "ca.yahoo.com")

    # dict of useful information to send in the email
    team_info = {}

    for league in config.CONFIG["leagues"]:
        team_info[league] = {}
        team_info[league]["website"] = config.CONFIG["leagues"][league]
        team_info[league]["errors"]= {}
        team = config.CONFIG["leagues"][league]

        date = datetime.datetime.now()        
        formatted_date = format_date(date)
        # go to the page and start the players
        print "Setting lineup for {0} for team in {1}".format(formatted_date, league)
        driver.get(team)
        set_lineup = driver.find_element_by_link_text("Start Active Players")
        set_lineup.click()
        time.sleep(5)
        # obtain the current setup of the roster
        roster = get_roster(team)
        # get the errors associated with that team and date
        errors = get_errors(roster)
        team_info[league]["errors"][formatted_date] = errors

        time.sleep(5)

        # if it has been requested to set rosters at further dates
        # do so now
        for i in range(num_days):

            # find the new date
            date = date + datetime.timedelta(days = 1)
            formatted_date = format_date(date)
            print "Setting lineup for {0} for team in {1}".format(formatted_date, league)

            # find the webpage for that date and set the lineup
            date_page = "{0}/team?&date={1}&stat1=S&stat2=D".format(team,formatted_date)
            driver.get(date_page)
            set_lineup = driver.find_element_by_link_text("Start Active Players")
            set_lineup.click()

            time.sleep(5)
            
            # find the roster for that date and associated errors
            roster = get_roster(date_page)
            errors = get_errors(roster)

            team_info[league]["errors"][formatted_date] = errors

            time.sleep(5)

    print "Preparing email"
    m = email.message.Message()
    m['From'] = config.CONFIG["email"]["address"]
    m['To'] = config.CONFIG["email"]["address"]
    m['Subject'] = "Fantasy Hockey Update"

    my_payload = get_email_string(team_info)

    m.set_payload(my_payload);

    try:
        print("trying host and port...")

        smtpObj = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        smtpObj.login("alfred.e.kenny@gmail.com", config.CONFIG["email"]["app_pw"])

        print("sending mail...")

        smtpObj.sendmail(config.CONFIG["email"]["address"], config.CONFIG["email"]["address"], m.as_string())

        print("Succesfully sent email")

    except smtplib.SMTPException:
        print("Error: unable to send email")
        import traceback
        traceback.print_exc()

    driver.close()

    display.stop()

def format_date(date):

    """
    formatted date must be in the form of
    YYYY-MM-DD
    taking great care that the month and day are two digits long
    i.e. 1998-09-02
    """

    year = date.year
    month = date.month
    if month < 10:
        month = "0{}".format(month)
    day = date.day
    if day < 10:
        day = "0{}".format(day)

    return "{0}-{1}-{2}".format(year,month,day)

def get_roster(team_link):
    print "Obtaining roster"
    r = requests.get(team_link)
    soup = BeautifulSoup(r.content,'html.parser')

    skater_roster = soup.find(id="statTable0").tbody
    goalie_roster = soup.find(id="statTable1").tbody
    players = skater_roster.findAll('tr')
    goalies = goalie_roster.findAll('tr')

    to_return = []

    for player in (players + goalies):
        div = player.find('div', {'class': 'ysf-player-name Nowrap Grid-u Relative Lh-xs Ta-start'})
        status = player.find('span',{'class':'ysf-player-status F-injury Fz-xxs Grid-u Lh-xs Mend-xs'})

        links = player.findAll('a')
        playing = False
        for link in links:
            if "pm" in link.contents[0]:
                playing = True

        words = div.findAll(text=True)[:3]
        words = [str(x) for x in filter(lambda x: str(x) != ' ', words)]
        name = words[0]
        fantasy_position = player.find('span',{'class':"pos-label Miwpx-40 Mawpx-40 Px-sm"})
        fantasy_position = str(fantasy_position.findAll(text=True)[0])
        nhlteam, positions = re.split('-', words[1])

        status = str(status.find(text=True))
        status = "Healthy" if status == 'None' else status
        player_dict = {"name": name, 
            "team": nhlteam.strip(),
            "status": status,
            "positions": re.split("\W+", positions.strip()),
            "current_position": fantasy_position,
            "playing_today": playing}

        to_return.append(player_dict)

        # print player_dict

    return to_return

def get_errors(roster):
    print "Finding lineup errors"

    to_return = []

    # there are two possible errors:
    # 1) player is healthy and is in IR, IR+
    # 2) player is injured and is in not in IR, IR+

    # there are also two possible iffy situations:
    # 1) a player is day-to-day
    # 2) a player is benched and healthy (full lineup)

    injured_positions = ["IR","IR+"]
    injuries = ["Out", "Injured Reserve", "Not Active"]
    questionable = ["Day-to-Day"]

    for player in roster:
        if ((player["status"] in injuries) and (player["current_position"] not in injured_positions)) or \
            ((player["status"] not in injuries) and (player["current_position"] in injured_positions)) or \
            (player["status"] in questionable) or \
            ((player["status"] not in questionable + injuries) and (player["current_position"] == "BN") and \
                player["playing_today"]):

            to_return.append("{0} is listed as \"{1}\" and is set at position {2}".format(player["name"],
                player["status"], player["current_position"]))

    return to_return

def get_email_string(errors):
    header = "Notes\n---------------------------------------\n"
    payload = []
    for league in errors:
        payload.append("{}\n".format(league.upper()))
        payload.append("{}\n".format(errors[league]["website"]))
        for date in sorted(errors[league]["errors"].keys()):
            # print "league: {0}, date: {1}".format(league, date)
            payload.append("{}:\n".format(date))
            if len(errors[league]["errors"][date]) == 0:
                payload.append("\tNo errors\n")
            else:  
                for error in errors[league]["errors"][date]:
                    payload.append("\t{}\n".format(error))

            # print "".join(payload)

        payload.append("\n")

    return "".join(payload)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        main(0)
    else:
        main(int(sys.argv[1]) - 1)
