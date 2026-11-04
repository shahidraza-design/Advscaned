import { useNavigate, useParams } from 'react-router-dom';
import { BadgeCheck, CalendarDays, MessageCircle, MapPin, Star, ThumbsUp, Clock } from 'lucide-react';
import { TopBar } from '../components/TopBar';
import { AdCard } from '../components/AdCard';
import { Avatar, EmptyState } from '../components/ui';
import { useStore } from '../lib/store';
import { useSeller } from '../lib/hooks';

export default function SellerProfile() {
  const { id } = useParams();
  const seller = useSeller(id ?? 'u1');
  const ads = useStore((s) => s.ads);
  const startChat = useStore((s) => s.startChat);
  const navigate = useNavigate();

  const listings = ads.filter((a) => a.sellerId === seller.id && a.status === 'active');

  const message = () => {
    if (!listings[0]) {
      navigate('/search');
      return;
    }
    navigate(`/chats/${startChat(listings[0].id)}`);
  };

  return (
    <div className="mx-auto max-w-[1280px]">
      <TopBar back title="Seller profile" />

      <div className="px-4 pt-4 lg:px-6">
        <div
          className="relative overflow-hidden rounded-2xl p-4 text-white"
          style={{ background: 'linear-gradient(130deg,#1F2937,#0F3D3A 70%,#067A66)' }}
        >
          <div className="absolute -right-10 -top-12 h-36 w-36 rounded-full bg-white/10 blur-2xl" />
          <div className="relative flex items-center gap-3">
            <Avatar name={seller.name} color={seller.avatarColor} size={60} ring />
            <div className="min-w-0 flex-1">
              <p className="flex items-center gap-1.5 text-[18px] font-extrabold">
                {seller.name}
                {seller.verified && <BadgeCheck size={17} className="text-brand-200" />}
              </p>
              <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11.5px] text-white/70">
                <span className="flex items-center gap-1">
                  <Star size={11} className="fill-accent-400 text-accent-400" /> {seller.rating} ·{' '}
                  {seller.reviews} reviews
                </span>
                <span className="flex items-center gap-1">
                  <CalendarDays size={11} /> since {seller.joined}
                </span>
              </p>
            </div>
          </div>
          {seller.bio && <p className="relative mt-3 text-[12px] leading-relaxed text-white/75">{seller.bio}</p>}
          <div className="relative mt-3 grid grid-cols-3 divide-x divide-white/15 rounded-xl bg-white/10 py-2 backdrop-blur">
            {[
              [listings.length, 'Live ads'],
              [`${seller.responseRate}%`, 'Response'],
              [seller.responseTime.replace('within ', ''), 'Reply time'],
            ].map(([v, l]) => (
              <div key={String(l)} className="text-center">
                <p className="text-[14px] font-extrabold leading-none">{v}</p>
                <p className="mt-0.5 text-[9.5px] uppercase tracking-wider text-white/60">{l}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-3 grid gap-2 sm:grid-cols-3">
          <button onClick={message} className="btn btn-primary sm:col-span-1">
            <MessageCircle size={16} /> Message seller
          </button>
          <div className="flex items-center gap-2 rounded-xl border px-3 py-2.5 text-[11.5px] text-muted hairline sm:col-span-2">
            <ThumbsUp size={14} className="text-brand-500" />
            Phones verified · responds {seller.responseTime} · member since {seller.joined}
          </div>
        </div>

        <h2 className="mb-2 mt-6 text-[15px] font-bold">Listings by {seller.name.split(' ')[0]}</h2>
        {listings.length === 0 ? (
          <EmptyState icon={<MapPin size={24} />} title="No live ads" body="This seller has no active listings right now." />
        ) : (
          <div className="grid grid-cols-2 gap-3 pb-4 sm:grid-cols-3 lg:grid-cols-4 lg:gap-4">
            {listings.map((ad) => (
              <AdCard key={ad.id} ad={ad} />
            ))}
          </div>
        )}

        <div className="mb-6 rounded-2xl border p-4 hairline" style={{ background: 'var(--surface)' }}>
          <p className="flex items-center gap-1.5 text-[13px] font-bold">
            <Clock size={14} className="text-brand-500" /> Response behaviour
          </p>
          <div className="mt-2 space-y-2">
            {[
              ['Replies to chats', `${seller.responseRate}%`],
              ['Median reply time', seller.responseTime],
              ['Deals completed', `${Math.max(3, Math.round(seller.reviews * 1.6))}`],
            ].map(([k, v]) => (
              <div key={k} className="flex items-center justify-between text-[12px]">
                <span className="text-muted">{k}</span>
                <span className="font-semibold">{v}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
