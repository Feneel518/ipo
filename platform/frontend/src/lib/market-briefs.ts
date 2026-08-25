import { displayCompanyName, displayDate, money, priceBand, quantity } from "./format";
import type { IpoCardData, IpoDetailData, Subscription, Summary } from "./types";

type LeadCandidate = IpoCardData & Partial<Pick<IpoDetailData, "issue_size_crore" | "subscriptions">>;

function companyName(ipo: IpoCardData) {
  return displayCompanyName(ipo.company_name).replace(/ Limited$/i, "");
}

function joinNames(names: string[]) {
  if (names.length < 2) return names[0] ?? "";
  if (names.length === 2) return `${names[0]} and ${names[1]}`;
  return `${names.slice(0, -1).join(", ")} and ${names.at(-1)}`;
}

function wordsBelowThousand(value: number): string {
  const small = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"];
  const tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"];
  if (value < 20) return small[value];
  if (value < 100) return `${tens[Math.floor(value / 10)]}${value % 10 ? `-${small[value % 10]}` : ""}`;
  return `${small[Math.floor(value / 100)]} hundred${value % 100 ? ` ${wordsBelowThousand(value % 100)}` : ""}`;
}

function numberWords(value: number | null | undefined) {
  const count = value ?? 0;
  if (!Number.isSafeInteger(count) || count < 0 || count >= 100_000) return count.toLocaleString("en-IN");
  if (count < 1_000) return wordsBelowThousand(count);
  const thousands = Math.floor(count / 1_000);
  return `${wordsBelowThousand(thousands)} thousand${count % 1_000 ? ` ${wordsBelowThousand(count % 1_000)}` : ""}`;
}

function sentenceNumber(value: number) {
  const words = numberWords(value);
  return words.charAt(0).toLocaleUpperCase("en-IN") + words.slice(1);
}

function date(value: string) {
  return displayDate(value, { day: "numeric", month: "long" });
}

function compareDate(field: keyof Pick<IpoCardData, "open_date" | "close_date" | "listing_date">) {
  return (left: IpoCardData, right: IpoCardData) => (left[field] ?? "9999-12-31").localeCompare(right[field] ?? "9999-12-31");
}

export function isMainboard(ipo: IpoCardData) {
  return ipo.listings.some((listing) => listing.segment === "MAINBOARD" && !listing.is_stale);
}

function hasLiveSubscriptions(ipo: LeadCandidate) {
  return ipo.subscriptions?.some((row) => row.captured_at && row.calculated_subscription != null) ?? false;
}

function issueSize(ipo: LeadCandidate) {
  const value = Number(ipo.issue_size_crore);
  return Number.isFinite(value) ? value : -1;
}

function overallSubscription(ipo: LeadCandidate) {
  const subscriptions = ipo.subscriptions ?? [];
  const latestCaptured = subscriptions.reduce(
    (latest, row) => row.captured_at > latest ? row.captured_at : latest,
    "",
  );
  const overall = subscriptions.find((row) =>
    row.captured_at === latestCaptured && /^(total|overall)$/i.test(row.category),
  );
  if (overall?.calculated_subscription == null) return null;
  const value = Number(overall?.calculated_subscription);
  return Number.isFinite(value) ? value : null;
}

function compareLeadPriority(left: LeadCandidate, right: LeadCandidate) {
  const leftSubscription = overallSubscription(left);
  const rightSubscription = overallSubscription(right);
  if (leftSubscription != null || rightSubscription != null) {
    if (leftSubscription == null) return 1;
    if (rightSubscription == null) return -1;
    const subscriptionDifference = rightSubscription - leftSubscription;
    if (subscriptionDifference) return subscriptionDifference;
  }
  if (hasLiveSubscriptions(left) !== hasLiveSubscriptions(right)) return hasLiveSubscriptions(left) ? -1 : 1;
  if (hasLiveSubscriptions(left)) {
    const sizeDifference = issueSize(right) - issueSize(left);
    if (sizeDifference) return sizeDifference;
  }
  return compareDate("close_date")(left, right) || left.id - right.id;
}

export function leadCandidatePool(ipos: IpoCardData[]) {
  const mainboard = ipos.filter(isMainboard);
  return mainboard.length ? mainboard : ipos;
}

export function selectLeadIssue(openIpos: LeadCandidate[], upcomingIpos: IpoCardData[]) {
  if (openIpos.length) return [...openIpos].sort(compareLeadPriority)[0];
  return sortUpcoming(leadCandidatePool(upcomingIpos))[0] ?? null;
}

function subscriptionValue(rows: Subscription[], category: RegExp) {
  const row = rows.find((item) => category.test(item.category));
  const value = Number(row?.calculated_subscription);
  return Number.isFinite(value) ? value : null;
}

function multiple(value: number) {
  return value.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

export function leadIssueDeck(overall: number | null) {
  if (overall == null) return "The exchange book at a glance";
  if (overall <= 0) return "The book awaits its first confirmed bids";
  if (overall < 1) return "The book builds toward full cover";
  if (overall < 3) return "The issue is fully covered";
  if (overall < 10) return "Demand gathers pace across the book";
  return "The book records strong demand";
}

export function leadIssueStory(ipo: IpoDetailData, latestSubscriptions: Subscription[]) {
  const sentences: string[] = [];
  const opening = ipo.lifecycle === "UPCOMING" ? "Bidding opens" : "Bidding opened";
  const terms: string[] = [];
  if (ipo.price_low || ipo.price_high) terms.push(`at a band of ${priceBand(ipo.price_low, ipo.price_high)} a share`);
  const shareTerms: string[] = [];
  if (ipo.lot_size) shareTerms.push(`a lot of ${ipo.lot_size.toLocaleString("en-IN")} shares`);
  if (ipo.face_value) shareTerms.push(`a face value of ${money(ipo.face_value)}`);
  if (shareTerms.length) terms.push(`with ${shareTerms.join(" and ")}`);
  const termCopy = terms.join(", ");
  sentences.push(`${opening}${ipo.open_date ? ` ${displayDate(ipo.open_date, { day: "numeric", month: "long" })}` : " on a date to be announced"}${termCopy ? ` ${termCopy}` : ""}.`);

  const totalShares = ipo.issue_size_shares ?? ipo.reservation_summary?.total_issue_shares;
  const publicShares = ipo.reservation_summary?.net_offer_shares;
  if (totalShares) {
    const publicBook = publicShares && Number(publicShares) !== Number(totalShares)
      ? `, of which ${quantity(publicShares)} form the public book`
      : "";
    sentences.push(`The issue offers ${quantity(totalShares)} shares${publicBook}.`);
  }

  const overall = subscriptionValue(latestSubscriptions, /^(total|overall)$/i);
  if (overall != null) {
    const categoryValues = [
      ["the non-institutional pool", subscriptionValue(latestSubscriptions, /^NII$/i)],
      ["retail", subscriptionValue(latestSubscriptions, /^RETAIL$/i)],
      ["the institutional pool", subscriptionValue(latestSubscriptions, /^QIB$/i)],
    ].filter((item): item is [string, number] => item[1] != null).slice(0, 2);
    const categoryCopy = categoryValues.length === 2
      ? `, with ${categoryValues[0][0]} at ${multiple(categoryValues[0][1])} times and ${categoryValues[1][0]} at ${multiple(categoryValues[1][1])} times`
      : categoryValues.length === 1 ? `, with ${categoryValues[0][0]} at ${multiple(categoryValues[0][1])} times` : "";
    const capturedAt = latestSubscriptions.find((row) => /^(total|overall)$/i.test(row.category))?.captured_at;
    const tapeTime = capturedAt
      ? `As of the ${new Intl.DateTimeFormat("en-IN", { hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" }).format(new Date(capturedAt))} exchange tape, `
      : "At the latest exchange update, ";
    sentences.push(`${tapeTime}the overall book stood at ${multiple(overall)} times${categoryCopy}.`);
  }

  const schedule: string[] = [];
  if (ipo.close_date) schedule.push(`Bidding closes ${displayDate(ipo.close_date, { day: "numeric", month: "long" })}`);
  if (ipo.allotment_date) schedule.push(`allotment is ${ipo.allotment_date_is_estimated ? "estimated" : "scheduled"} for ${displayDate(ipo.allotment_date, { day: "numeric", month: "long" })}`);
  const listingDate = ipo.listing_date ?? ipo.expected_listing_date;
  if (listingDate) {
    const exchanges = [...new Set(ipo.listings.filter((listing) => !listing.is_stale).map((listing) => listing.exchange))];
    const venue = exchanges.length > 1 ? " on both exchanges" : exchanges.length === 1 ? ` on ${exchanges[0]}` : "";
    schedule.push(`listing is ${ipo.listing_date ? "scheduled" : "estimated"} for ${displayDate(listingDate, { day: "numeric", month: "long" })}${venue}`);
  }
  if (schedule.length) sentences.push(`${schedule.join("; ")}.`);

  return sentences.join(" ");
}

function editorialBand(ipo: IpoCardData) {
  const values = [ipo.price_low, ipo.price_high]
    .filter((value): value is string => Boolean(value))
    .map((value) => Math.abs(Number(value)))
    .filter(Number.isFinite)
    .sort((left, right) => left - right);
  if (!values.length) return null;
  const low = money(String(values[0]));
  const high = money(String(values.at(-1)));
  return low === high ? low : `${low} to ${high}`;
}

export function onTheClockBrief(openIpos: IpoCardData[], today: string, total = openIpos.length) {
  const count = total;
  if (!count) return "No issues are accepting bids at present.";

  const dated = openIpos.filter((ipo) => ipo.close_date).sort(compareDate("close_date"));
  if (!dated.length) return `${sentenceNumber(count)} ${count === 1 ? "issue is" : "issues are"} accepting bids across the mainboard and both SME platforms.`;

  const nextClose = dated[0].close_date!;
  const cohort = dated.filter((ipo) => ipo.close_date === nextClose);
  const names = joinNames(cohort.slice(0, 2).map(companyName));
  const closeCopy = `${sentenceNumber(cohort.length)} ${cohort.length === 1 ? "closes" : "close"} on ${date(nextClose)}`;
  const finalCopy = nextClose === today
    ? `${names} ${cohort.length === 1 ? "is in its final session" : "are in their final sessions"}`
    : `${names} ${cohort.length === 1 ? "is due to close then" : "are due to close then"}`;
  return `${sentenceNumber(count)} ${count === 1 ? "issue is" : "issues are"} accepting bids across the mainboard and both SME platforms. ${closeCopy}; ${finalCopy}.`;
}

export function nextInLineBrief(upcomingIpos: IpoCardData[]) {
  const dated = upcomingIpos.filter((ipo) => ipo.open_date).sort(compareDate("open_date"));
  if (!dated.length) return "New issues are awaiting dates on the primary-market calendar.";

  const firstDate = dated[0].open_date!;
  const firstCohort = dated.filter((ipo) => ipo.open_date === firstDate);
  const firstNames = joinNames(firstCohort.slice(0, 2).map(companyName));
  const more = Math.max(0, firstCohort.length - 2);
  const subject = more ? `${firstNames} and ${numberWords(more)} more` : firstNames;
  let copy = `${subject} ${firstCohort.length === 1 ? "opens" : "open"} ${date(firstDate)}`;

  const following = dated.find((ipo) => ipo.open_date !== firstDate);
  if (following) {
    const band = editorialBand(following);
    copy += `; ${companyName(following)} follows on ${date(following.open_date!)}${band ? ` with a band of ${band} a share` : ""}`;
  }
  return `${copy}.`;
}

export function firstDayBrief(summary: Summary, listedIpos: IpoCardData[]) {
  const listedSme = summary.listed_sme ?? summary.sme;
  const countCopy = `${sentenceNumber(summary.listed)} ${summary.listed === 1 ? "issue has" : "issues have"} completed listing in the record, ${numberWords(listedSme)} of ${summary.listed === 1 ? "it" : "them"} on SME segments.`;
  const latest = [...listedIpos].filter((ipo) => ipo.listing_date).sort((left, right) => compareDate("listing_date")(right, left)).slice(0, 2);
  if (!latest.length) return countCopy;
  if (latest.length === 1) return `${countCopy} ${companyName(latest[0])} listed on ${date(latest[0].listing_date!)}.`;
  if (latest[0].listing_date === latest[1].listing_date) return `${countCopy} ${joinNames(latest.map(companyName))} listed on ${date(latest[0].listing_date!)}.`;
  return `${countCopy} ${companyName(latest[0])} listed on ${date(latest[0].listing_date!)} and ${companyName(latest[1])} on ${date(latest[1].listing_date!)}.`;
}

export function sortUpcoming(ipos: IpoCardData[]) {
  return [...ipos].sort(compareDate("open_date"));
}
