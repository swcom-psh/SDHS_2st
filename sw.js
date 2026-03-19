const CACHE_NAME = 'yaja-seating-v3';
const ASSETS_TO_CACHE = [
  './',
  './index.html',
  './manifest.json',
  './icon-192.png',
  './icon-512.png',
  './%EC%B5%9C%EC%A2%85csv_2%ED%95%99%EB%85%84%20%EC%95%BC%EC%9E%90.csv',
  'https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css'
];

// 서비스 워커 설치 및 캐싱
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('Opened cache');
        // 개별적으로 캐시하여 하나가 실패해도 나머지는 저장되도록 시도 (선택 사항)
        // 여기서는 다시 한 번 전체 캐싱을 시도하되, 오류를 잡아냅니다.
        return cache.addAll(ASSETS_TO_CACHE).catch(err => {
          console.error('Core assets caching failed:', err);
        });
      })
  );
});

// 기존 캐시 삭제 및 업데이트
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cache) => {
          if (cache !== CACHE_NAME) {
            return caches.delete(cache);
          }
        })
      );
    })
  );
});

// 네트워크 우선, 실패 시 캐시 반환 (Stale-while-revalidate 느낌으로 구현하거나 Cache-first)
// 여기서는 오프라인 지원을 위해 Cache-first (이미 있으면 캐시 사용) 전략을 사용합니다.
self.addEventListener('fetch', (event) => {
  event.respondWith(
    caches.match(event.request).then((response) => {
      return response || fetch(event.request);
    })
  );
});
