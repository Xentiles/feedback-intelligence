FROM node:24.15.0-alpine AS build

WORKDIR /app

COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

COPY apps/web/ .
RUN npm run build

FROM nginxinc/nginx-unprivileged:stable-alpine AS runtime

COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
COPY LICENSE NOTICE LICENSE-SCOPE.md THIRD_PARTY_NOTICES.md /usr/share/nginx/html/
COPY LICENSES /usr/share/nginx/html/LICENSES

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
