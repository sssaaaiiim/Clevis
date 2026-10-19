export const PINCHTAB_PATHS = {
  profiles: "/profiles",
  profile: (profileId: string) => `/profiles/${encodeURIComponent(profileId)}`,
  instancesStart: "/instances/start",
  instanceClose: (instanceId: string) => `/instances/${encodeURIComponent(instanceId)}/close`,
  instanceTabsOpen: (instanceId: string) => `/instances/${encodeURIComponent(instanceId)}/tabs/open`,
  tabNavigate: (tabId: string) => `/tabs/${encodeURIComponent(tabId)}/navigate`,
  tabSnapshot: (tabId: string) => `/tabs/${encodeURIComponent(tabId)}/snapshot`,
  tabAction: (tabId: string) => `/tabs/${encodeURIComponent(tabId)}/action`,
  tabText: (tabId: string) => `/tabs/${encodeURIComponent(tabId)}/text`,
  tabScreenshot: (tabId: string) => `/tabs/${encodeURIComponent(tabId)}/screenshot`,
} as const;
