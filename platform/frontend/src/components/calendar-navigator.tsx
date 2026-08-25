"use client";

import { ArrowUp, CalendarSearch } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

type CalendarNavigatorProps = {
  availableDatesByFilter: Record<CalendarFilter, string[]>;
  displayedMonth: string;
  initialDate: string;
  initialFilter: CalendarFilter;
  today: string;
};

export type CalendarFilter = "all" | "open" | "close" | "funds-free" | "allotment";

const filters: Array<{ value: CalendarFilter; label: string; eventType?: string }> = [
  { value: "all", label: "All" },
  { value: "open", label: "Open", eventType: "OPENS" },
  { value: "close", label: "Close", eventType: "CLOSES" },
  { value: "funds-free", label: "Funds free", eventType: "REFUNDS" },
  { value: "allotment", label: "Allotment", eventType: "ALLOTMENT" },
];

function nearestAvailableDate(target: string, availableDates: string[]) {
  if (!availableDates.length) return null;

  return availableDates.reduce((nearest, date) => {
    const nearestDistance = Math.abs(Date.parse(`${nearest}T00:00:00`) - Date.parse(`${target}T00:00:00`));
    const distance = Math.abs(Date.parse(`${date}T00:00:00`) - Date.parse(`${target}T00:00:00`));
    return distance < nearestDistance ? date : nearest;
  });
}

function scrollToDate(target: string, availableDates: string[], behavior: ScrollBehavior) {
  const date = nearestAvailableDate(target, availableDates);
  if (!date) return;

  document.getElementById(`date-${date}`)?.scrollIntoView({ behavior, block: "center" });
}

export function CalendarNavigator({ availableDatesByFilter, displayedMonth, initialDate, initialFilter, today }: CalendarNavigatorProps) {
  const defaultDate = initialDate || (displayedMonth === today.slice(0, 7) ? today : "");
  const [selectedDate, setSelectedDate] = useState(defaultDate);
  const [activeFilter, setActiveFilter] = useState<CalendarFilter>(initialFilter);
  const [showTop, setShowTop] = useState(false);
  const availableDates = availableDatesByFilter[activeFilter];

  useEffect(() => {
    const eventType = filters.find((filter) => filter.value === activeFilter)?.eventType;
    const calendar = document.querySelector(".gazette-calendar");
    if (!calendar) return;

    calendar.querySelectorAll<HTMLElement>("[data-calendar-event]").forEach((event) => {
      event.hidden = Boolean(eventType && event.dataset.calendarEvent !== eventType);
    });
    calendar.querySelectorAll<HTMLElement>("[data-calendar-day]").forEach((day) => {
      day.hidden = !day.querySelector("[data-calendar-event]:not([hidden])");
    });
  }, [activeFilter]);

  useEffect(() => {
    const target = initialDate || (displayedMonth === today.slice(0, 7) ? today : null);
    if (!target) return;

    const frame = window.requestAnimationFrame(() => scrollToDate(target, availableDates, "smooth"));
    return () => window.cancelAnimationFrame(frame);
  }, [availableDates, displayedMonth, initialDate, today]);

  useEffect(() => {
    const updateTopButton = () => setShowTop(window.scrollY > 500);
    updateTopButton();
    window.addEventListener("scroll", updateTopButton, { passive: true });
    return () => window.removeEventListener("scroll", updateTopButton);
  }, []);

  function jumpToDate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedDate) return;

    const selectedMonth = selectedDate.slice(0, 7);
    if (selectedMonth !== displayedMonth) {
      const query = new URLSearchParams({ month: selectedMonth, date: selectedDate });
      if (activeFilter !== "all") query.set("type", activeFilter);
      window.location.assign(`/calendar?${query.toString()}`);
      return;
    }

    const query = new URLSearchParams({ month: displayedMonth, date: selectedDate });
    if (activeFilter !== "all") query.set("type", activeFilter);
    window.history.replaceState(null, "", `/calendar?${query.toString()}`);
    scrollToDate(selectedDate, availableDates, "smooth");
  }

  function selectFilter(filter: CalendarFilter) {
    setActiveFilter(filter);
    const url = new URL(window.location.href);
    if (filter === "all") url.searchParams.delete("type");
    else url.searchParams.set("type", filter);
    window.history.replaceState(null, "", `${url.pathname}${url.search}`);
  }

  return (
    <>
      <div className="calendar-tools">
        <div className="calendar-type-filters" role="group" aria-label="Filter calendar dates">
          {filters.map((filter) => <button
            className={activeFilter === filter.value ? "active" : ""}
            type="button"
            aria-pressed={activeFilter === filter.value}
            onClick={() => selectFilter(filter.value)}
            key={filter.value}
          >{filter.label}</button>)}
        </div>
        <form className="calendar-jump" onSubmit={jumpToDate}>
          <label htmlFor="calendar-jump-date">Go to date</label>
          <input
            id="calendar-jump-date"
            type="date"
            value={selectedDate}
            onChange={(event) => setSelectedDate(event.target.value)}
          />
          <button type="submit" aria-label="Go to selected date">
            <CalendarSearch aria-hidden="true" size={16} strokeWidth={1.7} />
            <span>Go</span>
          </button>
        </form>
      </div>
      {activeFilter !== "all" && !availableDates.length && <p className="calendar-filter-empty" role="status">No matching dates are reported for this month.</p>}
      <button
        className={`calendar-to-top${showTop ? " is-visible" : ""}`}
        type="button"
        aria-label="Back to top"
        onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
      >
        <ArrowUp aria-hidden="true" size={18} strokeWidth={1.7} />
      </button>
    </>
  );
}
