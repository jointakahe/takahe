![takahē](static/img/logo-128.png)

A *very experimental* Fediverse server for microblogging/"toots". Not fully functional yet -
I'm still working on making all the basic bits work! For more background and information,
see [my blog posts about it](https://aeracode.org/category/takahe/).

Indended features:

* Can run on serverless hosting (no need for worker daemons)
* Multiple account domains possible per server
* Async evented core for fan-out/delivery
* Mastodon client API compatible (eventually)


## Deployment

### Requirements:

- **Python** 3.11
- **PostgreSQL** 14+
- **Lots of patience** This is *very experimental*

### Setup

More deployment docs will come soon! Just know that you need to run the Takahē
Django app, and then either hit `/.stator/runner/` or run `./manage.py runstator`
at least every 30 seconds.

## Roadmap

Takahē is still under very active development towards something I'm willing to
call a beta. I've grouped features here into milestones, along with if they're
done yet or not. None of this is final, and the further into the future it is,
the less sure I am about it.

### Alpha

- [x] Create posts
- [x] Set post visibility
- [x] Receive posts
- [x] Handle received post visibility (unlisted vs public only)
- [x] Receive post deletions
- [x] Receive post edits
- [x] Set content warnings on posts
- [x] Show content warnings on posts
- [x] Receive images on posts
- [x] Receive reply info
- [x] Create boosts
- [x] Receive boosts
- [x] Create likes
- [x] Receive likes
- [x] Create follows
- [x] Undo follows
- [x] Receive and accept follows
- [x] Receive follow undos
- [ ] Do outgoing mentions properly
- [x] Home timeline (posts and boosts from follows)
- [x] Notifications page (followed, boosted, liked)
- [x] Local timeline
- [x] Federated timeline
- [x] Profile pages
- [x] Settable icon and background image for profiles
- [x] User search
- [x] Following page
- [x] Followers page
- [x] Multiple domain support
- [x] Multiple identity support
- [x] Serverless-friendly worker subsystem
- [x] Settings subsystem
- [x] Server management page
- [x] Domain management page
- [x] Email subsystem
- [x] Signup flow
- [x] Password reset flow

### Beta

- [ ] Attach images to posts
- [ ] Edit posts
- [ ] Delete posts
- [ ] Password change flow
- [ ] Fetch remote post images locally and thumbnail
- [ ] Show follow pending states
- [ ] Manual approval of followers
- [ ] Reply threading on post creation
- [ ] Display posts with reply threads
- [ ] Create polls on posts
- [ ] Receive polls on posts
- [ ] Emoji fetching and display
- [ ] Emoji creation
- [ ] Image descriptions
- [ ] Hashtag search
- [ ] Flag for moderation
- [ ] Moderation queue
- [ ] User management page
- [ ] Server defederation
- [ ] Filters for posts/boosts
- [ ] OAuth subsystem

### 1.0

- [ ] IP banning
- [ ] Trends subsystem and moderation
- [ ] Server announcements
- [ ] Automated post deletion
- [ ] Post popularity system (for long gaps between timeline views)
- [ ] Mastodon client API

### Future

- [ ] Relays?
- [ ] Mastodon backup import? (would need url mapping for actors)

## Contributing

If you'd like to contribute, please read [CONTRIBUTING.md](./CONTRIBUTING.md).
