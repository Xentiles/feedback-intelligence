FROM mcr.microsoft.com/dotnet/sdk:10.0.401 AS build
WORKDIR /source

COPY ["services/api/Directory.Build.props", "."]
COPY ["services/api/src/FeedbackIntelligence.Api/FeedbackIntelligence.Api.csproj", "src/FeedbackIntelligence.Api/"]
COPY ["services/api/src/FeedbackIntelligence.Api/packages.lock.json", "src/FeedbackIntelligence.Api/"]
RUN dotnet restore "src/FeedbackIntelligence.Api/FeedbackIntelligence.Api.csproj" --locked-mode

COPY ["services/api/src/FeedbackIntelligence.Api/", "src/FeedbackIntelligence.Api/"]
RUN dotnet publish "src/FeedbackIntelligence.Api/FeedbackIntelligence.Api.csproj" \
    --configuration Release \
    --no-restore \
    --output /app/publish
COPY LICENSE NOTICE LICENSE-SCOPE.md THIRD_PARTY_NOTICES.md /app/publish/
COPY LICENSES /app/publish/LICENSES

FROM mcr.microsoft.com/dotnet/aspnet:10.0.12 AS final
WORKDIR /app
ENV ASPNETCORE_HTTP_PORTS=8080
EXPOSE 8080
COPY --from=build --chown=$APP_UID:$APP_UID /app/publish .
USER $APP_UID
ENTRYPOINT ["dotnet", "FeedbackIntelligence.Api.dll"]
