#!/usr/bin/env python3
"""
Get metadata about messages in a Gmail inbox, grouped by thread.

Updated for Python 3 + security (2026).
Use Gmail App Password: https://myaccount.google.com/apppasswords
"""

import imaplib
import re
from collections import defaultdict
from dateutil.parser import parser
from dateutil.tz import tzlocal
from email.parser import HeaderParser
from functools import partial
import sys

message_index_re = re.compile(r'^(\d+) \(')
thread_id_re = re.compile(r'X-GM-THRID (\d+)')

date_parser = parser()
header_parser = HeaderParser()

def message_info_from_tuple(unread_indices, m):
    parsed_headers = header_parser.parsestr(m[1].decode('utf-8', errors='replace'))
    parsed_lowercase_headers = {k.lower(): parsed_headers[k] for k in parsed_headers.keys()}

    return {
        'thread_id': thread_id_re.search(m[0].decode() if isinstance(m[0], bytes) else m[0]).group(1),
        'unread': message_index_re.search(m[0].decode() if isinstance(m[0], bytes) else m[0]).group(1) in unread_indices,
        'date': parsed_lowercase_headers['date'],
        'subject': parsed_lowercase_headers.get('subject', ''),
        'from': parsed_lowercase_headers.get('from', '')
    }

def parse_date_from_message_dict(info):
    date = info['date']

    try:
        parsed = date_parser.parse(date)
    except ValueError:
        # e.g. "Fri, 15 Apr 2016 02:45:07 -0700 (GMT-07:00)"
        parsed = date_parser.parse(re.sub(r'\([^)]+\)', '', date))

    if parsed.tzinfo is None:
        # dateutil doesn't understand these...
        unfortunate_tz_strings = [('EST', '-0500'), ('EDT', '-0400'), ('(GMT+00:00)', '(GMT)')]
        for tz_str, offset in unfortunate_tz_strings:
            date = date.replace(tz_str, offset)
            parsed = date_parser.parse(date)

    # Parsed dates are used for sorting, but not in the output,
    # so we can afford to be lenient with bad timezones.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tzlocal())

    return parsed

def gmail_thread_info(email, password):
    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(email, password)

        mail.select('INBOX')

        _, (uid_list,) = mail.uid('search', None, 'ALL')

        if uid_list == b'':
            print("No emails found.")
            return []

        uids = uid_list.split()
        # Limit to recent 100 UIDs for large inboxes (adjust as needed)
        uids = uids[-100:]
        uid_str = b','.join(uids)
        _, inbox = mail.uid('fetch', uid_str, '(X-GM-THRID BODY.PEEK[HEADER])')

        _, (unread_indices,) = mail.search(None, '(UNSEEN)')
        unread_indices = [idx.decode() for idx in unread_indices.split()]

        # every other "message" is the string ")"
        actual_messages = [inbox[i] for i in range(0, len(inbox), 2)]
        thread_infos = list(map(partial(message_info_from_tuple, unread_indices), actual_messages))

        # Group messages into Gmail threads
        thread_id_to_messages = defaultdict(list)
        for m in thread_infos:
            thread_id_to_messages[m['thread_id']].append(m)

        # Summarize each thread
        summarized_threads = []
        for thread_id, messages in thread_id_to_messages.items():
            sorted_by_date = sorted(messages, key=parse_date_from_message_dict)
            summarized_threads.append({
                # Take subject from the earliest message, which is least likely to have "Re:" in it
                'subject': sorted_by_date[0]['subject'],
                # Take date from the latest message
                'date': sorted_by_date[-1]['date'],
                'from': list(set(m['from'] for m in sorted_by_date)),
                'unread': any(m['unread'] for m in sorted_by_date),
                'thread_id': thread_id,
            })

        # Sort by timestamp
        return sorted(summarized_threads, key=parse_date_from_message_dict, reverse=True)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return []
    finally:
        try:
            mail.close()
            mail.logout()
        except:
            pass

if __name__ == "__main__":
    import secret

    threads = gmail_thread_info(secret.email, secret.password)
    print(f"\nRecent threads ({len(threads)} total):\n")
    for i, t in enumerate(threads[:10], 1):  # Top 10
        unread = " [UNREAD]" if t['unread'] else ""
        print(f"{i}. {t['subject']}{unread} | From: {', '.join(t['from'])} | Date: {t['date']}")
