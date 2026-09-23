"""页面“填入示例”按钮使用的示例邮件头。"""

SAMPLE_HEADERS = """\
Return-Path: <sender@example.com>
Received: from mailbox.final.example (127.0.0.1)
	by mailbox.final.example (Dovecot) with LMTP id zX92kQ
	for <user@final.example>; Tue, 23 Sep 2026 10:02:10 +0800 (CST)
Received: from mx1.final.example (mx1.final.example [198.51.100.10])
	by mailbox.final.example (Postfix) with ESMTPS id 7F3A2C9
	for <user@final.example>; Tue, 23 Sep 2026 10:02:10 +0800
Received: from relay2.provider.example (relay2.provider.example [203.0.113.22])
	by mx1.final.example (Postfix) with ESMTP id B4D91
	for <user@final.example>; Tue, 23 Sep 2026 10:02:05 +0800
Received: from relay1.provider.example (relay1.provider.example
	[203.0.113.11])
	by relay2.provider.example (Postfix) with ESMTP id 99C10
	for <user@final.example>; Tue, 23 Sep 2026 02:01:55 +0000 (UTC)
Received: from outgoing.example.org (outgoing.example.org [192.0.2.50])
	by relay1.provider.example (Postfix) with ESMTP id 41AB8
	for <user@final.example>; Tue, 23 Sep 2026 02:01:30 +0000
Received: from smtp01.corp.example.net (smtp01.corp.example.net [10.10.0.5])
	by outgoing.example.org with ESMTP
	for user@final.example
Received: from [10.10.0.5] (helo=smtp01.corp.example.net)
	by smtp01.corp.example.net with ESMTP id 88FF21
	for user@final.example; not-a-valid-date (server clock lost)
Date: Tue, 23 Sep 2026 02:00:00 +0000
From: Sender <sender@example.com>
To: User <user@final.example>
Subject: Delivery path demo
	with folding
Message-ID: <demo@example.com>
"""
