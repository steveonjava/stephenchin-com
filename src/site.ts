// SITE_MODE is read at build time only. Anything other than "production" builds the noindex preview.
export const IS_PREVIEW = process.env.SITE_MODE !== 'production';
export const SITE_URL = 'https://stephenchin.com';
export const SITE_NAME = 'Stephen Chin';
export const GITHUB_URL = 'https://github.com/steveonjava';

export const NAV = [
  { href: '/work/', label: 'Work' },
  { href: '/talks/', label: 'Talks' },
  { href: '/writing/', label: 'Writing' },
  { href: '/books/', label: 'Books' },
  { href: '/projects/', label: 'Projects' },
  { href: '/topics/', label: 'Topics' },
  { href: '/search/', label: 'Search' },
];

// Which record kinds each entry point lists. Community records appear under /work/ and in search.
export const SECTIONS = [
  { slug: 'talks', title: 'Talks and interviews', kinds: ['talk', 'video', 'interview'] },
  { slug: 'writing', title: 'Writing', kinds: ['article'] },
  { slug: 'books', title: 'Books', kinds: ['book'] },
  { slug: 'projects', title: 'Projects and code', kinds: ['project', 'code'] },
];
