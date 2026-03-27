const CACHE_NAME = 'yaja-seating-v22';
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
  self.skipWaiting(); // 새로운 서비스 워커가 즉시 활성화되도록 설정
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('Opened cache');
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
    }).then(() => self.clients.claim()) // 즉시 제어권 획득
  );
});

// 온라인상에서 무조건 최신 데이터를 먼저 받아오고, 실패 시에만 기존 캐시를 반환하는 Network-First (네트워크 우선) 전략
self.addEventListener('fetch', (event) => {
  event.respondWith(
    fetch(event.request)
      .catch(() => {
        // 네트워크 요청이 실패(ex: 오프라인)할 경우 캐시 확인
        return caches.match(event.request);
      })
  );
});
