import { map } from 'lodash/fp';

const SkeletonLine = ({ className = "" }) => (
  <div className={`bg-bg-elevated animate-pulse rounded ${className}`}></div>
);

const StockCardSkeleton = () => {
  return (
    <div className="bg-bg-secondary border border-border rounded-xl p-4 flex flex-col gap-4 shadow-sm">
      <div className="flex justify-between items-start">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <SkeletonLine className="h-6 w-20" />
            <SkeletonLine className="h-4 w-12" />
          </div>
          <SkeletonLine className="h-3 w-32 mt-1" />
        </div>
        <div className="text-right flex flex-col gap-1 items-end">
          <SkeletonLine className="h-5 w-16" />
          <SkeletonLine className="h-4 w-10" />
        </div>
      </div>

      <div className="flex justify-between items-center bg-bg-elevated p-2.5 rounded-lg border border-border">
        <div className="h-6 w-28 bg-bg-secondary animate-pulse rounded-full"></div>
        <div className="flex gap-2">
          {map(i => (
            <div key={i} className="h-5 w-8 bg-bg-secondary animate-pulse rounded"></div>
          ), [1, 2, 3])}
        </div>
      </div>

      <div className="flex flex-col gap-3">
        <div className="grid grid-cols-3 gap-2 border-b border-border pb-2.5">
          {map(i => (
            <div key={i} className="flex flex-col gap-1">
              <SkeletonLine className="h-2 w-8" />
              <SkeletonLine className="h-4 w-10" />
            </div>
          ), [1, 2, 3])}
        </div>
        <div className="grid grid-cols-3 gap-2">
          {map(i => (
            <div key={i} className="flex flex-col gap-1">
              <SkeletonLine className="h-2 w-8" />
              <SkeletonLine className="h-4 w-10" />
            </div>
          ), [1, 2, 3])}
        </div>
        <div className="grid grid-cols-3 gap-2 mt-1">
          {map(i => (
            <div key={i} className="flex flex-col gap-1">
              <SkeletonLine className="h-2 w-8" />
              <SkeletonLine className="h-4 w-10" />
            </div>
          ), [1, 2, 3])}
        </div>
      </div>
    </div>
  );
};

export default StockCardSkeleton;
