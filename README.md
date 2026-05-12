# Reputation Bot

Telegram bot for user reputation tracking.

## Description

This bot allows users to vote for each other's reputation in group chats. Each user can vote for another user once per day.

## Commands

- Reply to a message with `+rep` - Increase user reputation
- Reply to a message with `-rep` - Decrease user reputation
- `/mr` - Check your reputation
- `/cr` - View reputation leaderboard (top 20 positive and negative)

## Rules

- One vote per user per day
- Cannot vote for yourself
- Reply to user's message to vote

## Installation

```bash
git clone https://github.com/username/reputation-bot.git
cd reputation-bot
pip install -r requirements.txt
