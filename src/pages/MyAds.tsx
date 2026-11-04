import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  BarChart3,
  Eye,
  Heart,
  MessageCircle,
  PackageOpen,
  Pencil,
  Plus,
  Sparkles,
  Trash2,
  Zap,
} from 'lucide-react';
import { TopBar } from '../components/TopBar';
import { AdThumb } from '../components/AdCard';
import { Badge, EmptyState, Sheet } from '../components/ui';
import { toast, useStore } from '../lib/store';
import { cn, inr, timeAgo } from '../lib/utils';
import type { AdStatus } from '../lib/types';

const TABS: { id: AdStatus | 'all'; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'active', label: 'Live' },
  { id: 'sold', label: 'Sold' },
  { id: 'draft', label: 'Drafts' },
];

export default function MyAds() {
  const ads = useStore((s) => s.ads);
  const user = useStore((s) => s.user);
  const updateAd = useStore((s) => s.updateAd);
  const deleteAd = useStore((s) => s.deleteAd);
  const boostAd = useStore((s) => s.boostAd);
  const [tab, setTab] = useState<AdStatus | 'all'>('all');
  const [boostTarget, setBoostTarget] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const mine = useMemo(() => ads.filter((a) => a.sellerId === 'me'), [ads]);
  const filtered = tab === 'all' ? mine : mine.filter((a) => a.status === tab);

  const stats = useMemo(
    () => ({
      views: mine.reduce((n, a) => n + a.views, 0),
      saves: mine.reduce((n, a) => n + a.saves, 0),
      live: mine.filter((a) => a.status === 'active').length,
    }),
    [mine],
  );

  return (
    <div className="mx-auto max-w-3xl">
      <TopBar
        back="/profile"
        title="My ads"
        subtitle={`${stats.live} live · ${stats.views} total views`}
        right={
          <Link to="/post" className="btn btn-primary px-3 py-2 text-[12.5px]">
            <Plus size={15} /> Post
          </Link>
        }
      />

      <div className="px-4 pt-4">
        <div className="grid grid-cols-3 gap-2">
          {[
            { icon: Eye, label: 'Views', value: stats.views.toLocaleString('en-IN') },
            { icon: Heart, label: 'Saves', value: stats.saves },
            { icon: BarChart3, label: 'Live ads', value: stats.live },
          ].map(({ icon: Icon, label, value }) => (
            <div
              key={label}
              className="rounded-xl border p-3 hairline"
              style={{ background: 'var(--surface)' }}
            >
              <Icon size={15} className="text-brand-600 dark:text-brand-400" />
              <p className="mt-1.5 text-[18px] font-extrabold leading-none">{value}</p>
              <p className="mt-0.5 text-[10.5px] uppercase tracking-wider text-muted">{label}</p>
            </div>
          ))}
        </div>

        <div className="no-scrollbar -mx-4 mt-4 flex gap-2 overflow-x-auto px-4">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={cn('chip', tab === t.id && 'chip-on')}
            >
              {t.label}
              <span className="text-[10px] opacity-60">
                {t.id === 'all' ? mine.length : mine.filter((a) => a.status === t.id).length}
              </span>
            </button>
          ))}
        </div>

        {filtered.length === 0 ? (
          <EmptyState
            icon={<PackageOpen size={26} />}
            title={mine.length ? 'Nothing here' : 'You have not posted anything yet'}
            body={
              mine.length
                ? 'Ads you mark as sold or save as drafts will appear here.'
                : 'Turn unused things into cash — it takes less than a minute to post your first ad.'
            }
            action={mine.length ? undefined : 'Post an ad'}
            onAction={() => (window.location.href = '/post')}
          />
        ) : (
          <div className="mt-3 space-y-2.5 pb-4">
            {filtered.map((ad) => (
              <div
                key={ad.id}
                className="rounded-2xl border p-3 hairline"
                style={{ background: 'var(--surface)' }}
              >
                <div className="flex gap-3">
                  <Link
                    to={`/ad/${ad.id}`}
                    className="h-[76px] w-[76px] shrink-0 overflow-hidden rounded-xl bg-ink-100 dark:bg-white/5"
                  >
                    <AdThumb ad={ad} />
                  </Link>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-[15px] font-extrabold">{inr(ad.price)}</p>
                        <p className="truncate text-[12.5px] font-medium">{ad.title}</p>
                      </div>
                      <Badge
                        tone={
                          ad.status === 'active'
                            ? 'brand'
                            : ad.status === 'sold'
                              ? 'red'
                              : 'neutral'
                        }
                      >
                        {ad.status === 'active' ? 'Live' : ad.status === 'sold' ? 'Sold' : 'Draft'}
                      </Badge>
                    </div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10.5px] text-muted">
                      <span className="flex items-center gap-1">
                        <Eye size={10} /> {ad.views}
                      </span>
                      <span className="flex items-center gap-1">
                        <Heart size={10} /> {ad.saves}
                      </span>
                      <span>{timeAgo(ad.createdAt)}</span>
                      {ad.boosted && (
                        <span className="flex items-center gap-1 font-semibold text-accent-600">
                          <Zap size={10} /> Boosted
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                <div className="mt-2.5 flex gap-1.5 border-t pt-2.5 hairline">
                  <button
                    onClick={() => setBoostTarget(ad.id)}
                    disabled={ad.boosted}
                    className="flex flex-1 items-center justify-center gap-1 rounded-lg bg-accent-500/12 py-2 text-[11.5px] font-bold text-accent-600 disabled:opacity-40 dark:text-accent-400"
                  >
                    <Sparkles size={12} /> {ad.boosted ? 'Boosted' : 'Boost'}
                  </button>
                  <button
                    onClick={() => {
                      updateAd(ad.id, { status: ad.status === 'sold' ? 'active' : 'sold' });
                      toast(
                        ad.status === 'sold' ? 'Ad is live again' : 'Marked as sold 🎉',
                        'success',
                      );
                    }}
                    className="flex flex-1 items-center justify-center gap-1 rounded-lg bg-ink-100 py-2 text-[11.5px] font-bold dark:bg-white/10"
                  >
                    {ad.status === 'sold' ? 'Relist' : 'Mark sold'}
                  </button>
                  <Link
                    to={`/chats`}
                    className="flex flex-1 items-center justify-center gap-1 rounded-lg bg-ink-100 py-2 text-[11.5px] font-bold dark:bg-white/10"
                  >
                    <MessageCircle size={12} /> Chats
                  </Link>
                  <button
                    onClick={() => setConfirmDelete(ad.id)}
                    aria-label="Delete ad"
                    className="grid w-9 place-items-center rounded-lg bg-rose-50 text-rose-600 dark:bg-rose-500/15 dark:text-rose-300"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {mine.length > 0 && (
          <div className="mb-4 rounded-2xl border border-dashed p-4 hairline">
            <p className="flex items-center gap-1.5 text-[13px] font-bold">
              <Sparkles size={14} className="text-accent-500" /> Sell 3× faster with a boost
            </p>
            <p className="mt-1 text-[11.5px] leading-relaxed text-muted">
              Boosted ads appear at the top of nearby searches and in the “Featured today” rail for
              7 days. Demo only — no real payment is taken.
            </p>
          </div>
        )}
      </div>

      <Sheet open={!!boostTarget} onClose={() => setBoostTarget(null)} title="Boost this ad">
        <div className="rounded-2xl bg-gradient-to-br from-accent-500 to-orange-600 p-4 text-white">
          <p className="text-[11px] font-bold uppercase tracking-widest text-white/80">
            7-day boost
          </p>
          <p className="mt-1 text-[26px] font-extrabold">₹149</p>
          <p className="text-[12px] text-white/80">Featured placement + 3× more views</p>
        </div>
        <ul className="mt-3 space-y-2 text-[12.5px] text-muted">
          <li>• Top of category and search results in your city</li>
          <li>• “Featured” badge that builds buyer trust</li>
          <li>• Weekly performance report in notifications</li>
        </ul>
        <button
          onClick={() => {
            if (boostTarget) {
              boostAd(boostTarget);
              toast('Boost activated for 7 days 🚀', 'success', { label: 'View', to: '/myads' });
            }
            setBoostTarget(null);
          }}
          className="btn btn-primary mt-4 w-full"
        >
          <Zap size={16} /> Activate boost
        </button>
        <p className="mt-2 text-center text-[11px] text-muted">
          Demo checkout · no card required, nothing is charged.
        </p>
      </Sheet>

      <Sheet open={!!confirmDelete} onClose={() => setConfirmDelete(null)} title="Delete this ad?">
        <p className="text-[13px] text-muted">
          This removes the ad, its views and any boosts. Buyers with open chats will still see your
          messages, but the ad link will stop working.
        </p>
        <div className="mt-4 flex gap-2">
          <button onClick={() => setConfirmDelete(null)} className="btn btn-outline flex-1">
            Keep ad
          </button>
          <button
            onClick={() => {
              if (confirmDelete) deleteAd(confirmDelete);
              setConfirmDelete(null);
              toast('Ad deleted', 'info');
            }}
            className="btn flex-1 bg-rose-600 text-white"
          >
            Delete
          </button>
        </div>
      </Sheet>
    </div>
  );
}
