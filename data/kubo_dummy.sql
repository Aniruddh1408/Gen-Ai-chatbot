
-- To apply:
--   python scripts/apply_seed.py             (refuses on ENVIRONMENT=production)
--   python scripts/apply_seed.py --force     (override guard for demo/staging)


SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS '';


--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


--
-- Name: eventcategoryenum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.eventcategoryenum AS ENUM (
    'alert',
    'new_resident',
    'fall_alert',
    'suspected_alert',
    'confirmed_fall',
    'false_alert',
    'forwarded',
    'test',
    'resolved',
    'movement',
    'zenzo_call',
    'unresolved_alert',
    'escalated',
    'dim_movement',
    'out_of_bed',
    'out_of_room'
);


--
-- Name: genderenum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.genderenum AS ENUM (
    'male',
    'female',
    'other'
);


--
-- Name: insightpriorityenum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.insightpriorityenum AS ENUM (
    'low',
    'high',
    'mid'
);


--
-- Name: insighttypeenum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.insighttypeenum AS ENUM (
    'sleep',
    'activity',
    'vitals',
    'environment'
);


--
-- Name: objectstatusenum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.objectstatusenum AS ENUM (
    'good',
    'no_response'
);


--
-- Name: objecttypeenum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.objecttypeenum AS ENUM (
    'furniture',
    'sensor',
    'sensor_fds',
    'sensor_vitals'
);


--
-- Name: roompos; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.roompos AS ENUM (
    'D',
    'L',
    'R',
    'U'
);


--
-- Name: severitytypeenum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.severitytypeenum AS ENUM (
    'LOW',
    'MEDIUM',
    'HIGH',
    'CRITICAL'
);


--
-- Name: sleepstageenum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.sleepstageenum AS ENUM (
    'light',
    'deep',
    'rem',
    'awake',
    'nonrem',
    'normal'
);


--
-- Name: sleeptypeenum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.sleeptypeenum AS ENUM (
    'night',
    'day'
);


--
-- Name: statusenum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.statusenum AS ENUM (
    'active',
    'inactive',
    'sleeping',
    'walking'
);


--
-- Name: statustypeenum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.statustypeenum AS ENUM (
    'OPEN',
    'CLOSED',
    'INVESTIGATING'
);


--
-- Name: summarytypeenum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.summarytypeenum AS ENUM (
    'sleep',
    'activity',
    'vitals',
    'environment',
    'fall'
);


--
-- Name: temperature_unit_enum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.temperature_unit_enum AS ENUM (
    'C',
    'F',
    'K'
);


--
-- Name: timeintervalenum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.timeintervalenum AS ENUM (
    'hourly',
    'daily'
);


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: activity_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.activity_log (
    id integer NOT NULL,
    object_id character varying NOT NULL,
    location character varying,
    resident_id integer NOT NULL,
    status public.statusenum NOT NULL,
    start_time timestamp with time zone NOT NULL,
    end_time timestamp with time zone NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: activity_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.activity_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: activity_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.activity_log_id_seq OWNED BY public.activity_log.id;


--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: ambience; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ambience (
    id bigint NOT NULL,
    ingestion_time timestamp with time zone NOT NULL,
    temp double precision,
    humidity double precision,
    board text,
    aqi_indoor double precision,
    aqi_outdoor double precision,
    ambient_noise double precision,
    "time" text,
    light double precision,
    aqi double precision,
    tvoc double precision,
    eco2 double precision,
    location text
);


--
-- Name: ambience_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ambience_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ambience_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ambience_id_seq OWNED BY public.ambience.id;


--
-- Name: analytics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.analytics (
    id integer NOT NULL,
    display_name character varying NOT NULL,
    dashboard_url character varying NOT NULL,
    is_active boolean,
    deleted_by integer,
    is_deleted boolean,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: analytics_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.analytics_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: analytics_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.analytics_id_seq OWNED BY public.analytics.id;


--
-- Name: community; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.community (
    id integer NOT NULL,
    name character varying NOT NULL,
    address character varying NOT NULL,
    capacity integer NOT NULL,
    total_resident integer NOT NULL,
    city character varying NOT NULL,
    timezone_info character varying DEFAULT 'Asia/Kolkata'::character varying NOT NULL,
    temperature_unit public.temperature_unit_enum NOT NULL,
    deleted_by integer,
    is_deleted boolean,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    home_type character varying DEFAULT 'model'::character varying NOT NULL,
    organisation_id integer NOT NULL
);


--
-- Name: community_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.community_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: community_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.community_id_seq OWNED BY public.community.id;


--
-- Name: community_user_mapping; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.community_user_mapping (
    id bigint NOT NULL,
    community_id integer NOT NULL,
    user_id integer NOT NULL,
    deleted_by integer,
    is_deleted boolean,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: community_user_mapping_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.community_user_mapping_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: community_user_mapping_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.community_user_mapping_id_seq OWNED BY public.community_user_mapping.id;


--
-- Name: documents_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.documents_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: fds; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.fds (
    id bigint NOT NULL,
    ingestion_time timestamp with time zone NOT NULL,
    type text,
    platform text,
    report text,
    board_sn text,
    location text,
    live integer,
    fn bigint,
    software_version text,
    "time" text,
    activity integer,
    "position" text,
    result text
);


--
-- Name: fds_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.fds_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: fds_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.fds_id_seq OWNED BY public.fds.id;


--
-- Name: feedbacks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.feedbacks (
    id bigint NOT NULL,
    submitted_by integer NOT NULL,
    body text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: feedbacks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.feedbacks_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: feedbacks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.feedbacks_id_seq OWNED BY public.feedbacks.id;


--
-- Name: incidents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.incidents (
    id integer NOT NULL,
    room_id integer NOT NULL,
    event_category public.eventcategoryenum NOT NULL,
    event_outcome character varying NOT NULL,
    event_time timestamp with time zone NOT NULL,
    event_end_time timestamp with time zone,
    status boolean NOT NULL,
    object_id character varying NOT NULL,
    object_type character varying NOT NULL,
    json_payload jsonb,
    deleted_by integer,
    is_deleted boolean,
    resolve_type public.eventcategoryenum,
    action_status jsonb,
    call_status jsonb,
    escalation_level integer,
    last_escalation_time timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: incidents_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.incidents_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: incidents_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.incidents_id_seq OWNED BY public.incidents.id;


--
-- Name: insights; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.insights (
    id bigint NOT NULL,
    resident_id integer NOT NULL,
    board character varying NOT NULL,
    type public.insighttypeenum NOT NULL,
    priority public.insightpriorityenum NOT NULL,
    meta_data jsonb,
    location text,
    date date NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    insight character varying
);


--
-- Name: insights_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.insights_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: insights_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.insights_id_seq OWNED BY public.insights.id;


--
-- Name: motion; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.motion (
    id bigint NOT NULL,
    ingestion_time timestamp with time zone NOT NULL,
    bodysigns double precision,
    distance double precision,
    x double precision,
    y double precision,
    z double precision,
    board text
);


--
-- Name: motion_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.motion_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: motion_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.motion_id_seq OWNED BY public.motion.id;


--
-- Name: movement_mapping; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.movement_mapping (
    id bigint NOT NULL,
    ingestion_time timestamp with time zone NOT NULL,
    "time" character varying,
    board character varying,
    location character varying,
    movement_location character varying,
    object_name character varying,
    payload jsonb
);


--
-- Name: movement_mapping_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.movement_mapping_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: movement_mapping_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.movement_mapping_id_seq OWNED BY public.movement_mapping.id;


--
-- Name: movement_time; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.movement_time (
    id bigint NOT NULL,
    ingestion_time timestamp with time zone NOT NULL,
    payload jsonb
);


--
-- Name: movement_time_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.movement_time_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: movement_time_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.movement_time_id_seq OWNED BY public.movement_time.id;


--
-- Name: notifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notifications (
    id integer NOT NULL,
    event_category public.eventcategoryenum NOT NULL,
    event_time timestamp with time zone NOT NULL,
    resident_id integer,
    room_id integer,
    status boolean NOT NULL,
    message character varying,
    resolve_type public.eventcategoryenum,
    deleted_by integer,
    is_deleted boolean,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: notifications_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.notifications_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: notifications_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.notifications_id_seq OWNED BY public.notifications.id;


--
-- Name: obj; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.obj (
    id bigint NOT NULL,
    ingestion_time timestamp with time zone NOT NULL,
    "time" text,
    fn bigint,
    board text,
    location text,
    obj jsonb
);


--
-- Name: obj_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.obj_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: obj_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.obj_id_seq OWNED BY public.obj.id;


--
-- Name: objects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.objects (
    id integer NOT NULL,
    object_id character varying NOT NULL,
    location character varying,
    room_id integer NOT NULL,
    image character varying NOT NULL,
    start_x double precision NOT NULL,
    start_z double precision NOT NULL,
    end_x double precision NOT NULL,
    end_z double precision NOT NULL,
    rotation double precision NOT NULL,
    object_type public.objecttypeenum NOT NULL,
    status public.objectstatusenum NOT NULL,
    sos_id character varying,
    is_active boolean,
    device_status character varying,
    deleted_by integer,
    is_deleted boolean,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: objects_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.objects_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: objects_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.objects_id_seq OWNED BY public.objects.id;


--
-- Name: on_bed; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.on_bed (
    id bigint NOT NULL,
    ingestion_time timestamp with time zone NOT NULL,
    "time" character varying,
    board character varying,
    location character varying,
    on_bed boolean
);


--
-- Name: on_bed_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.on_bed_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: on_bed_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.on_bed_id_seq OWNED BY public.on_bed.id;


--
-- Name: organisation; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organisation (
    id integer NOT NULL,
    name character varying NOT NULL,
    city character varying NOT NULL,
    headquarters_address character varying NOT NULL,
    deleted_by integer,
    is_deleted boolean,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: organisation_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.organisation_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: organisation_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.organisation_id_seq OWNED BY public.organisation.id;


--
-- Name: push_endpoints; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.push_endpoints (
    id bigint NOT NULL,
    user_id integer NOT NULL,
    provider character varying NOT NULL,
    endpoint character varying NOT NULL,
    p256dh character varying,
    auth character varying,
    device_type character varying,
    device_id character varying,
    user_agent character varying,
    created_at timestamp with time zone DEFAULT now(),
    last_seen timestamp with time zone DEFAULT now(),
    is_valid boolean
);


--
-- Name: push_endpoints_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.push_endpoints_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: push_endpoints_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.push_endpoints_id_seq OWNED BY public.push_endpoints.id;


--
-- Name: resident_profile; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.resident_profile (
    id integer NOT NULL,
    image character varying NOT NULL,
    flat_number character varying NOT NULL,
    dob text NOT NULL,
    gender text NOT NULL,
    no_of_falls integer NOT NULL,
    is_deleted boolean,
    deleted_by integer,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    fall_alert boolean,
    fall_suspected boolean,
    movement_alert boolean,
    dim_light_alert boolean,
    outroom_alert boolean,
    outbed_alert boolean,
    distance_threshold double precision,
    call_from_mobile character varying(20),
    buzzer_config jsonb,
    emergency_contacts jsonb[],
    trigger_settings jsonb,
    medical_history text,
    name character varying NOT NULL
);


--
-- Name: resident_profile_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.resident_profile_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: resident_profile_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.resident_profile_id_seq OWNED BY public.resident_profile.id;


--
-- Name: roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.roles (
    id integer NOT NULL,
    name character varying NOT NULL,
    deleted_by integer,
    is_deleted boolean,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    permissions jsonb
);


--
-- Name: roles_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.roles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: roles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.roles_id_seq OWNED BY public.roles.id;


--
-- Name: room_resident_mapping; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.room_resident_mapping (
    id integer NOT NULL,
    resident_id integer NOT NULL,
    room_id integer NOT NULL,
    deleted_by integer,
    is_deleted boolean,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: room_resident_mapping_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.room_resident_mapping_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: room_resident_mapping_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.room_resident_mapping_id_seq OWNED BY public.room_resident_mapping.id;


--
-- Name: rooms; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rooms (
    id integer NOT NULL,
    room_name character varying(100) NOT NULL,
    community_id integer NOT NULL,
    width double precision NOT NULL,
    length double precision NOT NULL,
    room_pos public.roompos NOT NULL,
    deleted_by integer,
    is_deleted boolean,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: rooms_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.rooms_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: rooms_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.rooms_id_seq OWNED BY public.rooms.id;


--
-- Name: security_incidents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.security_incidents (
    id bigint NOT NULL,
    date date NOT NULL,
    description text NOT NULL,
    severity public.severitytypeenum NOT NULL,
    status public.statustypeenum NOT NULL,
    closed_date date,
    is_resolved boolean NOT NULL,
    remark text,
    closed_by integer,
    is_deleted boolean,
    deleted_by integer,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: security_incidents_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.security_incidents_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: security_incidents_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.security_incidents_id_seq OWNED BY public.security_incidents.id;


--
-- Name: service_alert; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_alert (
    id bigint NOT NULL,
    ingestion_time timestamp with time zone NOT NULL,
    service_name character varying,
    slug character varying,
    status boolean
);


--
-- Name: service_alert_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.service_alert_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: service_alert_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.service_alert_id_seq OWNED BY public.service_alert.id;


--
-- Name: sleep_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sleep_sessions (
    id integer NOT NULL,
    board character varying NOT NULL,
    sleep_stage public.sleepstageenum NOT NULL,
    start_duration timestamp with time zone NOT NULL,
    end_duration timestamp with time zone NOT NULL,
    sleep_type public.sleeptypeenum NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: sleep_sessions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sleep_sessions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sleep_sessions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sleep_sessions_id_seq OWNED BY public.sleep_sessions.id;


--
-- Name: sos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sos (
    id bigint NOT NULL,
    ingestion_time timestamp with time zone NOT NULL,
    "time" character varying,
    board character varying,
    button_action character varying,
    sos_id character varying
);


--
-- Name: sos_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sos_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sos_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sos_id_seq OWNED BY public.sos.id;


--
-- Name: state_machine_binary; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.state_machine_binary (
    id bigint NOT NULL,
    ingestion_time timestamp with time zone NOT NULL,
    "time" text,
    board text,
    location text,
    payload jsonb,
    multiple_people text
);


--
-- Name: state_machine_binary_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.state_machine_binary_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: state_machine_binary_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.state_machine_binary_id_seq OWNED BY public.state_machine_binary.id;


--
-- Name: tenant_credentials; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tenant_credentials (
    id integer NOT NULL,
    api_key character varying NOT NULL,
    api_secret_hash character varying NOT NULL,
    is_active boolean NOT NULL,
    expires_at timestamp with time zone,
    last_used_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    tenant_id uuid NOT NULL
);


--
-- Name: tenant_credentials_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tenant_credentials_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tenant_credentials_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tenant_credentials_id_seq OWNED BY public.tenant_credentials.id;


--
-- Name: tenants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tenants (
    name character varying NOT NULL,
    status character varying NOT NULL,
    expires_at timestamp with time zone,
    config_version integer NOT NULL,
    integration_config jsonb NOT NULL,
    is_deleted boolean NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    id uuid DEFAULT gen_random_uuid() NOT NULL
);


--
-- Name: toss; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.toss (
    id bigint NOT NULL,
    ingestion_time timestamp with time zone NOT NULL,
    "time" character varying,
    board character varying,
    location character varying
);


--
-- Name: toss_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.toss_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: toss_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.toss_id_seq OWNED BY public.toss.id;


--
-- Name: user_hierarchy_mapping; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_hierarchy_mapping (
    id integer NOT NULL,
    parent_id integer NOT NULL,
    child_id integer NOT NULL,
    is_deleted boolean,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: user_hierarchy_mapping_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_hierarchy_mapping_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_hierarchy_mapping_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_hierarchy_mapping_id_seq OWNED BY public.user_hierarchy_mapping.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    mobile character varying(15),
    country_code character varying(10) NOT NULL,
    name character varying(100) NOT NULL,
    organization character varying(100),
    email character varying(120),
    pin character varying,
    deleted_by integer,
    is_deleted boolean,
    last_login timestamp with time zone NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    role_id integer NOT NULL,
    city character varying,
    address character varying,
    attribute jsonb,
    add_permissions jsonb,
    remove_permissions jsonb,
    timezone_info character varying DEFAULT 'Asia/Kolkata'::character varying NOT NULL,
    first_login boolean NOT NULL,
    rate_limit_config jsonb
);


--
-- Name: users_analytics_mapping; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users_analytics_mapping (
    id integer NOT NULL,
    user_id integer NOT NULL,
    analytics_id integer NOT NULL,
    deleted_by integer,
    is_deleted boolean,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: users_analytics_mapping_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_analytics_mapping_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_analytics_mapping_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_analytics_mapping_id_seq OWNED BY public.users_analytics_mapping.id;


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: vitals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vitals (
    id bigint NOT NULL,
    ingestion_time timestamp with time zone NOT NULL,
    hr double precision,
    rr double precision,
    board text
);


--
-- Name: vitals_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.vitals_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: vitals_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.vitals_id_seq OWNED BY public.vitals.id;


--
-- Name: vw_resident_sensor; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.vw_resident_sensor AS
 SELECT o.id AS object_pk,
    o.object_id,
    o.object_type,
    o.status AS object_status,
    o.is_active AS object_is_active,
    o.location AS object_location,
    o.device_status,
    r.id AS room_id,
    r.room_name,
    r.room_pos,
    c.id AS community_id,
    c.name AS community_name,
    c.organisation_id,
    rrm.resident_id,
    rp.name AS resident_name,
    rp.flat_number AS resident_flat,
    rp.dob AS resident_dob,
    rp.gender AS resident_gender,
    rp.no_of_falls AS resident_no_of_falls,
    rp.fall_alert AS resident_fall_alert
   FROM ((((public.objects o
     JOIN public.rooms r ON (((r.id = o.room_id) AND (COALESCE(r.is_deleted, false) = false))))
     JOIN public.community c ON (((c.id = r.community_id) AND (COALESCE(c.is_deleted, false) = false))))
     LEFT JOIN public.room_resident_mapping rrm ON (((rrm.room_id = r.id) AND (COALESCE(rrm.is_deleted, false) = false))))
     LEFT JOIN public.resident_profile rp ON (((rp.id = rrm.resident_id) AND (COALESCE(rp.is_deleted, false) = false))))
  WHERE (COALESCE(o.is_deleted, false) = false);


--
-- Name: webhook_outbox; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.webhook_outbox (
    id integer NOT NULL,
    event_id character varying NOT NULL,
    alert_type character varying NOT NULL,
    device_id character varying NOT NULL,
    payload jsonb NOT NULL,
    status character varying NOT NULL,
    attempts integer NOT NULL,
    next_attempt_at timestamp with time zone NOT NULL,
    last_error character varying,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    delivered_at timestamp with time zone,
    tenant_id uuid NOT NULL
);


--
-- Name: webhook_outbox_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.webhook_outbox_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: webhook_outbox_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.webhook_outbox_id_seq OWNED BY public.webhook_outbox.id;


--
-- Name: wellness_metrics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.wellness_metrics (
    id bigint NOT NULL,
    board character varying NOT NULL,
    type public.summarytypeenum NOT NULL,
    time_interval public.timeintervalenum NOT NULL,
    attribute jsonb,
    location text,
    score double precision,
    date date NOT NULL,
    start_time timestamp with time zone NOT NULL,
    end_time timestamp with time zone NOT NULL
);


--
-- Name: wellness_metrics_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.wellness_metrics_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: wellness_metrics_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.wellness_metrics_id_seq OWNED BY public.wellness_metrics.id;


--
-- Name: activity_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activity_log ALTER COLUMN id SET DEFAULT nextval('public.activity_log_id_seq'::regclass);


--
-- Name: ambience id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ambience ALTER COLUMN id SET DEFAULT nextval('public.ambience_id_seq'::regclass);


--
-- Name: analytics id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics ALTER COLUMN id SET DEFAULT nextval('public.analytics_id_seq'::regclass);


--
-- Name: community id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community ALTER COLUMN id SET DEFAULT nextval('public.community_id_seq'::regclass);


--
-- Name: community_user_mapping id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_user_mapping ALTER COLUMN id SET DEFAULT nextval('public.community_user_mapping_id_seq'::regclass);


--
-- Name: fds id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fds ALTER COLUMN id SET DEFAULT nextval('public.fds_id_seq'::regclass);


--
-- Name: feedbacks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.feedbacks ALTER COLUMN id SET DEFAULT nextval('public.feedbacks_id_seq'::regclass);


--
-- Name: incidents id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incidents ALTER COLUMN id SET DEFAULT nextval('public.incidents_id_seq'::regclass);


--
-- Name: insights id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insights ALTER COLUMN id SET DEFAULT nextval('public.insights_id_seq'::regclass);


--
-- Name: motion id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.motion ALTER COLUMN id SET DEFAULT nextval('public.motion_id_seq'::regclass);


--
-- Name: movement_mapping id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.movement_mapping ALTER COLUMN id SET DEFAULT nextval('public.movement_mapping_id_seq'::regclass);


--
-- Name: movement_time id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.movement_time ALTER COLUMN id SET DEFAULT nextval('public.movement_time_id_seq'::regclass);


--
-- Name: notifications id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications ALTER COLUMN id SET DEFAULT nextval('public.notifications_id_seq'::regclass);


--
-- Name: obj id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.obj ALTER COLUMN id SET DEFAULT nextval('public.obj_id_seq'::regclass);


--
-- Name: objects id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.objects ALTER COLUMN id SET DEFAULT nextval('public.objects_id_seq'::regclass);


--
-- Name: on_bed id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.on_bed ALTER COLUMN id SET DEFAULT nextval('public.on_bed_id_seq'::regclass);


--
-- Name: organisation id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organisation ALTER COLUMN id SET DEFAULT nextval('public.organisation_id_seq'::regclass);


--
-- Name: push_endpoints id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.push_endpoints ALTER COLUMN id SET DEFAULT nextval('public.push_endpoints_id_seq'::regclass);


--
-- Name: resident_profile id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resident_profile ALTER COLUMN id SET DEFAULT nextval('public.resident_profile_id_seq'::regclass);


--
-- Name: roles id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles ALTER COLUMN id SET DEFAULT nextval('public.roles_id_seq'::regclass);


--
-- Name: room_resident_mapping id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.room_resident_mapping ALTER COLUMN id SET DEFAULT nextval('public.room_resident_mapping_id_seq'::regclass);


--
-- Name: rooms id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rooms ALTER COLUMN id SET DEFAULT nextval('public.rooms_id_seq'::regclass);


--
-- Name: security_incidents id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_incidents ALTER COLUMN id SET DEFAULT nextval('public.security_incidents_id_seq'::regclass);


--
-- Name: service_alert id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_alert ALTER COLUMN id SET DEFAULT nextval('public.service_alert_id_seq'::regclass);


--
-- Name: sleep_sessions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sleep_sessions ALTER COLUMN id SET DEFAULT nextval('public.sleep_sessions_id_seq'::regclass);


--
-- Name: sos id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sos ALTER COLUMN id SET DEFAULT nextval('public.sos_id_seq'::regclass);


--
-- Name: state_machine_binary id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.state_machine_binary ALTER COLUMN id SET DEFAULT nextval('public.state_machine_binary_id_seq'::regclass);


--
-- Name: tenant_credentials id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenant_credentials ALTER COLUMN id SET DEFAULT nextval('public.tenant_credentials_id_seq'::regclass);


--
-- Name: toss id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.toss ALTER COLUMN id SET DEFAULT nextval('public.toss_id_seq'::regclass);


--
-- Name: user_hierarchy_mapping id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_hierarchy_mapping ALTER COLUMN id SET DEFAULT nextval('public.user_hierarchy_mapping_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: users_analytics_mapping id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users_analytics_mapping ALTER COLUMN id SET DEFAULT nextval('public.users_analytics_mapping_id_seq'::regclass);


--
-- Name: vitals id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vitals ALTER COLUMN id SET DEFAULT nextval('public.vitals_id_seq'::regclass);


--
-- Name: webhook_outbox id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.webhook_outbox ALTER COLUMN id SET DEFAULT nextval('public.webhook_outbox_id_seq'::regclass);


--
-- Name: wellness_metrics id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wellness_metrics ALTER COLUMN id SET DEFAULT nextval('public.wellness_metrics_id_seq'::regclass);


--
-- Name: activity_log activity_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activity_log
    ADD CONSTRAINT activity_log_pkey PRIMARY KEY (id);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: ambience ambience_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ambience
    ADD CONSTRAINT ambience_pkey PRIMARY KEY (id, ingestion_time);


--
-- Name: analytics analytics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics
    ADD CONSTRAINT analytics_pkey PRIMARY KEY (id);


--
-- Name: community community_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community
    ADD CONSTRAINT community_pkey PRIMARY KEY (id);


--
-- Name: community_user_mapping community_user_mapping_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_user_mapping
    ADD CONSTRAINT community_user_mapping_pkey PRIMARY KEY (id);


--
-- Name: fds fds_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fds
    ADD CONSTRAINT fds_pkey PRIMARY KEY (id, ingestion_time);


--
-- Name: feedbacks feedbacks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.feedbacks
    ADD CONSTRAINT feedbacks_pkey PRIMARY KEY (id);


--
-- Name: incidents incidents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incidents
    ADD CONSTRAINT incidents_pkey PRIMARY KEY (id);


--
-- Name: insights insights_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insights
    ADD CONSTRAINT insights_pkey PRIMARY KEY (id);


--
-- Name: motion motion_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.motion
    ADD CONSTRAINT motion_pkey PRIMARY KEY (id, ingestion_time);


--
-- Name: movement_mapping movement_mapping_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.movement_mapping
    ADD CONSTRAINT movement_mapping_pkey PRIMARY KEY (id, ingestion_time);


--
-- Name: movement_time movement_time_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.movement_time
    ADD CONSTRAINT movement_time_pkey PRIMARY KEY (id, ingestion_time);


--
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);


--
-- Name: obj obj_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.obj
    ADD CONSTRAINT obj_pkey PRIMARY KEY (id, ingestion_time);


--
-- Name: objects objects_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.objects
    ADD CONSTRAINT objects_pkey PRIMARY KEY (id);


--
-- Name: on_bed on_bed_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.on_bed
    ADD CONSTRAINT on_bed_pkey PRIMARY KEY (id, ingestion_time);


--
-- Name: organisation organisation_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organisation
    ADD CONSTRAINT organisation_name_key UNIQUE (name);


--
-- Name: organisation organisation_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organisation
    ADD CONSTRAINT organisation_pkey PRIMARY KEY (id);


--
-- Name: push_endpoints push_endpoints_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.push_endpoints
    ADD CONSTRAINT push_endpoints_pkey PRIMARY KEY (id);


--
-- Name: resident_profile resident_profile_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resident_profile
    ADD CONSTRAINT resident_profile_pkey PRIMARY KEY (id);


--
-- Name: roles roles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (id);


--
-- Name: room_resident_mapping room_resident_mapping_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.room_resident_mapping
    ADD CONSTRAINT room_resident_mapping_pkey PRIMARY KEY (id);


--
-- Name: room_resident_mapping room_resident_mapping_room_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.room_resident_mapping
    ADD CONSTRAINT room_resident_mapping_room_id_key UNIQUE (room_id);


--
-- Name: rooms rooms_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rooms
    ADD CONSTRAINT rooms_pkey PRIMARY KEY (id);


--
-- Name: security_incidents security_incidents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_incidents
    ADD CONSTRAINT security_incidents_pkey PRIMARY KEY (id);


--
-- Name: service_alert service_alert_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_alert
    ADD CONSTRAINT service_alert_pkey PRIMARY KEY (id);


--
-- Name: sleep_sessions sleep_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sleep_sessions
    ADD CONSTRAINT sleep_sessions_pkey PRIMARY KEY (id);


--
-- Name: sos sos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sos
    ADD CONSTRAINT sos_pkey PRIMARY KEY (id, ingestion_time);


--
-- Name: state_machine_binary state_machine_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.state_machine_binary
    ADD CONSTRAINT state_machine_pkey PRIMARY KEY (id, ingestion_time);


--
-- Name: tenant_credentials tenant_credentials_api_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenant_credentials
    ADD CONSTRAINT tenant_credentials_api_key_key UNIQUE (api_key);


--
-- Name: tenant_credentials tenant_credentials_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenant_credentials
    ADD CONSTRAINT tenant_credentials_pkey PRIMARY KEY (id);


--
-- Name: tenants tenants_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT tenants_pkey PRIMARY KEY (id);


--
-- Name: toss toss_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.toss
    ADD CONSTRAINT toss_pkey PRIMARY KEY (id, ingestion_time);


--
-- Name: webhook_outbox uq_tenant_webhook_event; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.webhook_outbox
    ADD CONSTRAINT uq_tenant_webhook_event UNIQUE (tenant_id, event_id);


--
-- Name: push_endpoints uq_user_device; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.push_endpoints
    ADD CONSTRAINT uq_user_device UNIQUE (user_id, device_type, user_agent);


--
-- Name: user_hierarchy_mapping user_hierarchy_mapping_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_hierarchy_mapping
    ADD CONSTRAINT user_hierarchy_mapping_pkey PRIMARY KEY (id);


--
-- Name: users_analytics_mapping users_analytics_mapping_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users_analytics_mapping
    ADD CONSTRAINT users_analytics_mapping_pkey PRIMARY KEY (id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_mobile_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_mobile_key UNIQUE (mobile);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: vitals vitals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vitals
    ADD CONSTRAINT vitals_pkey PRIMARY KEY (id, ingestion_time);


--
-- Name: webhook_outbox webhook_outbox_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.webhook_outbox
    ADD CONSTRAINT webhook_outbox_pkey PRIMARY KEY (id);


--
-- Name: wellness_metrics wellness_metrics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wellness_metrics
    ADD CONSTRAINT wellness_metrics_pkey PRIMARY KEY (id);


--
-- Name: idx_ingestion_time_ambience_v2; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ingestion_time_ambience_v2 ON public.ambience USING btree (ingestion_time);


--
-- Name: idx_ingestion_time_fds_v2; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ingestion_time_fds_v2 ON public.fds USING btree (ingestion_time);


--
-- Name: idx_ingestion_time_motion_v2; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ingestion_time_motion_v2 ON public.motion USING btree (ingestion_time);


--
-- Name: idx_ingestion_time_movement_mapping_v2; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ingestion_time_movement_mapping_v2 ON public.movement_mapping USING btree (ingestion_time);


--
-- Name: idx_ingestion_time_movement_time_v2; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ingestion_time_movement_time_v2 ON public.movement_time USING btree (ingestion_time);


--
-- Name: idx_ingestion_time_obj_v2; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ingestion_time_obj_v2 ON public.obj USING btree (ingestion_time);


--
-- Name: idx_ingestion_time_on_bed_v2; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ingestion_time_on_bed_v2 ON public.on_bed USING btree (ingestion_time);


--
-- Name: idx_ingestion_time_sos_v2; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ingestion_time_sos_v2 ON public.sos USING btree (ingestion_time);


--
-- Name: idx_ingestion_time_state_machine; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ingestion_time_state_machine ON public.state_machine_binary USING btree (ingestion_time);


--
-- Name: idx_ingestion_time_toss_v2; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ingestion_time_toss_v2 ON public.toss USING btree (ingestion_time);


--
-- Name: idx_ingestion_time_vitals_v2; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ingestion_time_vitals_v2 ON public.vitals USING btree (ingestion_time);


--
-- Name: ix_community_user_mapping_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_community_user_mapping_id ON public.community_user_mapping USING btree (id);


--
-- Name: ix_resident_profile_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_resident_profile_id ON public.resident_profile USING btree (id);


--
-- Name: ix_roles_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_roles_id ON public.roles USING btree (id);


--
-- Name: ix_room_resident_mapping_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_room_resident_mapping_id ON public.room_resident_mapping USING btree (id);


--
-- Name: ix_rooms_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rooms_id ON public.rooms USING btree (id);


--
-- Name: ix_security_incidents_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_security_incidents_id ON public.security_incidents USING btree (id);


--
-- Name: ix_sleep_sessions_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sleep_sessions_id ON public.sleep_sessions USING btree (id);


--
-- Name: ix_tenant_credentials_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tenant_credentials_tenant_id ON public.tenant_credentials USING btree (tenant_id);


--
-- Name: ix_tenants_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tenants_id ON public.tenants USING btree (id);


--
-- Name: ix_tenants_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_tenants_name ON public.tenants USING btree (name);


--
-- Name: ix_user_hierarchy_mapping_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_hierarchy_mapping_id ON public.user_hierarchy_mapping USING btree (id);


--
-- Name: ix_users_analytics_mapping_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_analytics_mapping_id ON public.users_analytics_mapping USING btree (id);


--
-- Name: ix_users_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_id ON public.users USING btree (id);


--
-- Name: ix_webhook_outbox_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_webhook_outbox_tenant_id ON public.webhook_outbox USING btree (tenant_id);


--
-- Name: activity_log activity_log_resident_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activity_log
    ADD CONSTRAINT activity_log_resident_id_fkey FOREIGN KEY (resident_id) REFERENCES public.resident_profile(id);


--
-- Name: analytics analytics_deleted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics
    ADD CONSTRAINT analytics_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public.users(id);


--
-- Name: community community_deleted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community
    ADD CONSTRAINT community_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public.users(id);


--
-- Name: community community_organisation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community
    ADD CONSTRAINT community_organisation_id_fkey FOREIGN KEY (organisation_id) REFERENCES public.organisation(id);


--
-- Name: community_user_mapping community_user_mapping_community_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_user_mapping
    ADD CONSTRAINT community_user_mapping_community_id_fkey FOREIGN KEY (community_id) REFERENCES public.community(id);


--
-- Name: community_user_mapping community_user_mapping_deleted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_user_mapping
    ADD CONSTRAINT community_user_mapping_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public.users(id);


--
-- Name: community_user_mapping community_user_mapping_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_user_mapping
    ADD CONSTRAINT community_user_mapping_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: feedbacks feedbacks_submitted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.feedbacks
    ADD CONSTRAINT feedbacks_submitted_by_fkey FOREIGN KEY (submitted_by) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: incidents incidents_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incidents
    ADD CONSTRAINT incidents_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.rooms(id);


--
-- Name: insights insights_resident_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insights
    ADD CONSTRAINT insights_resident_id_fkey FOREIGN KEY (resident_id) REFERENCES public.resident_profile(id) ON DELETE CASCADE;


--
-- Name: notifications notifications_deleted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public.users(id);


--
-- Name: notifications notifications_resident_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_resident_id_fkey FOREIGN KEY (resident_id) REFERENCES public.resident_profile(id);


--
-- Name: notifications notifications_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.rooms(id);


--
-- Name: objects objects_deleted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.objects
    ADD CONSTRAINT objects_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public.users(id);


--
-- Name: objects objects_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.objects
    ADD CONSTRAINT objects_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.rooms(id);


--
-- Name: organisation organisation_deleted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organisation
    ADD CONSTRAINT organisation_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public.users(id);


--
-- Name: push_endpoints push_endpoints_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.push_endpoints
    ADD CONSTRAINT push_endpoints_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: resident_profile resident_profile_deleted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resident_profile
    ADD CONSTRAINT resident_profile_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public.users(id);


--
-- Name: room_resident_mapping room_resident_mapping_deleted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.room_resident_mapping
    ADD CONSTRAINT room_resident_mapping_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public.users(id);


--
-- Name: room_resident_mapping room_resident_mapping_resident_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.room_resident_mapping
    ADD CONSTRAINT room_resident_mapping_resident_id_fkey FOREIGN KEY (resident_id) REFERENCES public.resident_profile(id);


--
-- Name: room_resident_mapping room_resident_mapping_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.room_resident_mapping
    ADD CONSTRAINT room_resident_mapping_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.rooms(id);


--
-- Name: rooms rooms_community_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rooms
    ADD CONSTRAINT rooms_community_id_fkey FOREIGN KEY (community_id) REFERENCES public.community(id);


--
-- Name: rooms rooms_deleted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rooms
    ADD CONSTRAINT rooms_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public.users(id);


--
-- Name: security_incidents security_incidents_closed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_incidents
    ADD CONSTRAINT security_incidents_closed_by_fkey FOREIGN KEY (closed_by) REFERENCES public.users(id);


--
-- Name: security_incidents security_incidents_deleted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_incidents
    ADD CONSTRAINT security_incidents_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public.users(id);


--
-- Name: tenant_credentials tenant_credentials_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenant_credentials
    ADD CONSTRAINT tenant_credentials_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: user_hierarchy_mapping user_hierarchy_mapping_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_hierarchy_mapping
    ADD CONSTRAINT user_hierarchy_mapping_child_id_fkey FOREIGN KEY (child_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_hierarchy_mapping user_hierarchy_mapping_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_hierarchy_mapping
    ADD CONSTRAINT user_hierarchy_mapping_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: users_analytics_mapping users_analytics_mapping_analytics_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users_analytics_mapping
    ADD CONSTRAINT users_analytics_mapping_analytics_id_fkey FOREIGN KEY (analytics_id) REFERENCES public.analytics(id);


--
-- Name: users_analytics_mapping users_analytics_mapping_deleted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users_analytics_mapping
    ADD CONSTRAINT users_analytics_mapping_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public.users(id);


--
-- Name: users_analytics_mapping users_analytics_mapping_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users_analytics_mapping
    ADD CONSTRAINT users_analytics_mapping_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: users users_deleted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public.users(id);


--
-- Name: users users_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id);


--
-- Name: webhook_outbox webhook_outbox_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.webhook_outbox
    ADD CONSTRAINT webhook_outbox_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- PostgreSQL database dump complete
--
-- (psql meta-command \unrestrict was removed: psycopg2 cannot execute
--  psql client meta-commands and aborts the whole file on the first one.)


BEGIN;

-- ===========================================================================
-- PHASE A — SCHEMA MIGRATION
-- ===========================================================================

-- A1. Drop the view first; otherwise it pins resident_profile.resident_id
-- and blocks the column drop.
DROP VIEW IF EXISTS public.vw_resident_sensor;

-- A2. Drop every FK that currently keys resident_id off users.id.
-- Idempotent so a re-run is safe.
ALTER TABLE public.resident_profile
    DROP CONSTRAINT IF EXISTS resident_profile_resident_id_fkey;
ALTER TABLE public.room_resident_mapping
    DROP CONSTRAINT IF EXISTS room_resident_mapping_resident_id_fkey;
ALTER TABLE public.activity_log
    DROP CONSTRAINT IF EXISTS activity_log_resident_id_fkey;
ALTER TABLE public.insights
    DROP CONSTRAINT IF EXISTS insights_resident_id_fkey;
ALTER TABLE public.notifications
    DROP CONSTRAINT IF EXISTS notifications_resident_id_fkey;

-- A3. Wipe seeded data BEFORE altering columns. Three reasons:
--   1) DROP COLUMN on a populated table is fine, but ADD COLUMN ... NOT NULL
--      without a default would fail with existing rows.
--   2) Re-running with stale data could leave invalid FK pointers between
--      old rows and the new schema.
--   3) The four resident_id FKs (activity_log, insights, notifications,
--      incidents/room) were just dropped in A2 — so CASCADE on
--      resident_profile would NOT follow into them. They must be listed
--      here explicitly, otherwise stale rows survive A3 and break A6's
--      ADD CONSTRAINT validation.
TRUNCATE TABLE
    public.activity_log,
    public.insights,
    public.notifications,
    public.incidents,
    public.room_resident_mapping,
    public.objects,
    public.resident_profile,
    public.rooms,
    public.community_user_mapping,
    public.community,
    public.users,
    public.organisation,
    public.roles
RESTART IDENTITY CASCADE;

-- A4. resident_profile.resident_id is now redundant (== id). Drop it.
ALTER TABLE public.resident_profile
    DROP COLUMN IF EXISTS resident_id;

-- A5. resident_profile gains the name column that previously lived on users.
ALTER TABLE public.resident_profile
    ADD COLUMN IF NOT EXISTS name character varying NOT NULL;

-- A6. Repoint the four remaining resident_id FKs at resident_profile(id).
-- Done after the truncate + column changes so the new constraints validate
-- against an empty table.
ALTER TABLE public.room_resident_mapping
    ADD CONSTRAINT room_resident_mapping_resident_id_fkey
    FOREIGN KEY (resident_id) REFERENCES public.resident_profile(id);
ALTER TABLE public.activity_log
    ADD CONSTRAINT activity_log_resident_id_fkey
    FOREIGN KEY (resident_id) REFERENCES public.resident_profile(id);
ALTER TABLE public.insights
    ADD CONSTRAINT insights_resident_id_fkey
    FOREIGN KEY (resident_id) REFERENCES public.resident_profile(id) ON DELETE CASCADE;
ALTER TABLE public.notifications
    ADD CONSTRAINT notifications_resident_id_fkey
    FOREIGN KEY (resident_id) REFERENCES public.resident_profile(id);

-- ===========================================================================
-- PHASE B — DATA SEED
-- ===========================================================================

-- B1. roles
INSERT INTO public.roles (id, name, permissions, created_at, updated_at) VALUES
  (1, 'admin',         '{"scope":"organisation","read":["*"],"write":["*"]}'::jsonb, now(), now()),
  (2, 'center_owner',  '{"scope":"community","read":["*"],"write":["resident","room","object"]}'::jsonb, now(), now()),
  (3, 'caregiver',     '{"scope":"community","read":["resident","incident","vitals","activity"],"write":[]}'::jsonb, now(), now());
SELECT setval('public.roles_id_seq', 3, true);

-- B2. organisation
INSERT INTO public.organisation (id, name, city, headquarters_address, created_at, updated_at) VALUES
  (1, 'Kubocare', 'Bengaluru', '1 Innovation Drive, Bengaluru, KA 560001', now(), now());
SELECT setval('public.organisation_id_seq', 1, true);

-- B3. users — only humans who log in. Residents are NOT users any more.
--     16 total: 1 admin + 5 center owners + 10 caregivers.

-- B3a. admin (id=1)
INSERT INTO public.users
  (id, name, email, mobile, country_code, pin, role_id,
   last_login, first_login, timezone_info, created_at, updated_at)
VALUES
  (1, 'Kubocare Admin', 'admin@kubocare.demo', '9100000001', '+91', 'demo0001', 1,
   now(), false, 'Asia/Kolkata', now(), now());

-- B3b. center_owners (id 2..6, one per community)
INSERT INTO public.users
  (id, name, email, mobile, country_code, pin, role_id,
   last_login, first_login, timezone_info, created_at, updated_at)
SELECT
   uid,
   'Center Owner ' || (uid - 1),
   'owner.c' || (uid - 1) || '@kubocare.demo',
   '91000000' || lpad(uid::text, 2, '0'),
   '+91',
   'demo' || lpad(uid::text, 4, '0'),
   2,
   now(), false, 'Asia/Kolkata', now(), now()
FROM generate_series(2, 6) AS uid;

-- B3c. caregivers (id 7..16, two per community)
INSERT INTO public.users
  (id, name, email, mobile, country_code, pin, role_id,
   last_login, first_login, timezone_info, created_at, updated_at)
SELECT
   uid,
   'Caregiver C' || (1 + (uid - 7) / 2) || '-' || (1 + (uid - 7) % 2),
   'caregiver' || uid || '@kubocare.demo',
   '91000000' || lpad(uid::text, 2, '0'),
   '+91',
   'demo' || lpad(uid::text, 4, '0'),
   3,
   now(), false, 'Asia/Kolkata', now(), now()
FROM generate_series(7, 16) AS uid;

SELECT setval('public.users_id_seq', 16, true);

-- B4. community
INSERT INTO public.community
  (id, name, address, capacity, total_resident, city,
   organisation_id, temperature_unit, home_type, timezone_info,
   created_at, updated_at)
VALUES
  (1, 'Green Valley Care',         'Plot 12, Indiranagar, Bengaluru',   20, 8, 'Bengaluru', 1, 'C', 'assisted_living', 'Asia/Kolkata', now(), now()),
  (2, 'Sunrise Senior Living',     '45 Banjara Hills, Hyderabad',       20, 8, 'Hyderabad', 1, 'C', 'assisted_living', 'Asia/Kolkata', now(), now()),
  (3, 'Lotus Wellness Home',       '7 Koregaon Park, Pune',             20, 8, 'Pune',      1, 'C', 'memory_care',     'Asia/Kolkata', now(), now()),
  (4, 'Maple Heights Eldercare',   '88 Jubilee Hills, Chennai',         20, 8, 'Chennai',   1, 'C', 'independent',     'Asia/Kolkata', now(), now()),
  (5, 'Coastal Haven Senior Home', '22 Marine Drive, Mumbai',           20, 8, 'Mumbai',    1, 'C', 'assisted_living', 'Asia/Kolkata', now(), now());
SELECT setval('public.community_id_seq', 5, true);

-- B5. community_user_mapping
--     admin -> all 5; each center_owner / caregiver -> exactly 1.
INSERT INTO public.community_user_mapping
  (community_id, user_id, created_at, updated_at)
SELECT c, 1, now(), now() FROM generate_series(1, 5) AS c
UNION ALL
SELECT uid - 1, uid, now(), now() FROM generate_series(2, 6) AS uid
UNION ALL
SELECT 1 + (uid - 7) / 2, uid, now(), now() FROM generate_series(7, 16) AS uid;

-- B6. rooms (8 per community, room_id 1..40)
INSERT INTO public.rooms
  (id, room_name, community_id, width, length, room_pos, created_at, updated_at)
SELECT
   rid,
   'Room ' || ((rid - 1) % 8 + 1),
   1 + (rid - 1) / 8,
   4.5,
   5.0,
   (ARRAY['D','L','R','U']::public.roompos[])[1 + ((rid - 1) % 4)],
   now(), now()
FROM generate_series(1, 40) AS rid;
SELECT setval('public.rooms_id_seq', 40, true);

-- B7. resident_profile (40 rows). Canonical residents table now.
--     name comes from this table (added in A5); no more users.name dependency.
-- Real-sounding Indian senior names instead of placeholder "Resident Cx-Ry".
-- Order matches the gender pattern below (m,f,f,m,f,m,f,f per community
-- block of 8). 15 male + 25 female total. The community a resident belongs
-- to is reachable via the room chain — there is no per-name prefix telling
-- you the community, on purpose: the user is staff of one community and
-- already knows which community they're viewing.
INSERT INTO public.resident_profile
  (id, name, image, flat_number, dob, gender, no_of_falls,
   fall_alert, fall_suspected, movement_alert, dim_light_alert,
   outroom_alert, outbed_alert, distance_threshold,
   emergency_contacts, medical_history, created_at, updated_at)
SELECT
   pid,
   -- 20 male + 20 female. Each slot's name matches the alternating gender
   -- pattern below (m,f,m,f,m,f,m,f per block of 8); swap them together if
   -- you ever rebalance.
   (ARRAY[
     -- Community 1 (pid 1..8)
     'Anil Sharma',       'Sunita Rao',          'Rajesh Iyer',       'Lakshmi Krishnan',
     'Vikram Mehta',      'Meera Devi',          'Ashok Banerjee',    'Kamala Iyengar',
     -- Community 2 (pid 9..16)
     'Suresh Reddy',      'Sushila Bhat',        'Ramesh Pillai',     'Radha Murthy',
     'Mahesh Joshi',      'Saraswati Menon',     'Krishna Iyengar',   'Pushpa Joshi',
     -- Community 3 (pid 17..24)
     'Arvind Nair',       'Vimala Subramanian',  'Deepak Verma',      'Saroja Kumar',
     'Pradeep Kulkarni',  'Geeta Pillai',        'Surendra Pai',      'Latha Shenoy',
     -- Community 4 (pid 25..32)
     'Sanjay Bose',       'Indira Pai',          'Mohan Rao',         'Padma Reddy',
     'Kamlesh Gupta',     'Shanti Nair',         'Hari Menon',        'Yamuna Kamath',
     -- Community 5 (pid 33..40)
     'Bharat Desai',      'Janaki Naidu',        'Naresh Patel',      'Bharati Bhandari',
     'Govind Krishnan',   'Anjali Kapoor',       'Devraj Kapoor',     'Usha Verma'
   ])[pid],
   'https://demo.kubocare/avatars/r' || pid || '.png',
   'F-' || ((pid - 1) % 8 + 1),
   (DATE '1940-01-01' + ((pid * 137) % 8000))::text,
   (ARRAY['male','female','male','female','male','female','male','female'])[1 + ((pid - 1) % 8)],
   0,
   true, true, true, true, true, true,
   1.5,
   ARRAY['{"name":"Family Contact","phone":"+919000099999","relation":"child"}'::jsonb],
   -- Distribute the medical-condition strings the text-search handler in
   -- app/retrievers/_sql/constants.py (_RESIDENT_TEXT_SEARCH_RULES) knows
   -- about. 8-slot pattern repeats across the 40 residents so every
   -- community has roughly the same condition mix. Slot 8 is "no major
   -- chronic illness" as the negative-control case.
   (ARRAY[
     'Hypertension; on routine review',
     'Type 2 Diabetes; diet and exercise plan',
     'Arthritis; mobility support recommended',
     'Asthma; salbutamol inhaler as needed',
     'Cardiovascular history; post-surgery recovery',
     'Osteoporosis; calcium and vitamin D supplementation',
     'Thyroid disorder; on levothyroxine',
     'No major chronic illness'
   ])[1 + ((pid - 1) % 8)],
   now(), now()
FROM generate_series(1, 40) AS pid;
SELECT setval('public.resident_profile_id_seq', 40, true);

-- B8. objects (2 per room: 1 bed + 1 KuboCare radar).
--     There is ONE radar device per room/resident; it handles fall detection,
--     bed algorithms, and vitals together. Its object_id is OBJ-(room*3) and
--     every sensor stream (vitals/sleep/wellness/incidents) joins to it via the
--     board / object_id columns. k=1 is the bed (furniture), k=3 is the radar;
--     the old k=2 fall-sensor row is gone (the radar covers falls too).
INSERT INTO public.objects
  (id, object_id, room_id, image,
   start_x, start_z, end_x, end_z, rotation,
   object_type, status, is_active,
   created_at, updated_at)
SELECT
   (rid - 1) * 3 + k,
   'OBJ-' || lpad(((rid - 1) * 3 + k)::text, 5, '0'),
   rid,
   CASE k WHEN 1 THEN 'bed.png' ELSE 'radar.png' END,
   0.0, 0.0, 1.0, 2.0, 0.0,
   (CASE k WHEN 1 THEN 'furniture' ELSE 'sensor' END)::public.objecttypeenum,
   'good'::public.objectstatusenum,
   true,
   now(), now()
FROM generate_series(1, 40) AS rid,
     unnest(ARRAY[1, 3]) AS k;
SELECT setval('public.objects_id_seq', 120, true);

-- B9. room_resident_mapping. resident_id is now resident_profile.id (1..40),
--     no longer users.id. Same 1:1 mapping shape (UNIQUE on room_id).
INSERT INTO public.room_resident_mapping
  (resident_id, room_id, created_at, updated_at)
SELECT n, n, now(), now()
FROM generate_series(1, 40) AS n;

-- ===========================================================================
-- PHASE C — SENSOR / WELLNESS DATA
-- ===========================================================================
-- Realistic-ish time series so the chatbot has something to answer for
-- vitals / sleep / activity / incident / insight queries. Volumes are
-- intentionally bounded (15 days, a handful of rows per resident per day)
-- — small enough to re-seed in seconds, large enough that "average HR over
-- the last week" returns a believable number. Every Phase C table covers the
-- same window: the 15 completed days [CURRENT_DATE-15 .. CURRENT_DATE-1].
--
-- Join chain reminder (new schema, post-migration):
--   sensor.board (text) -> objects.object_id (text)
--   objects.room_id -> rooms.id -> rooms.community_id    (community scope)
--   activity_log.resident_id / insights.resident_id /
--   notifications.resident_id -> resident_profile.id     (direct)
--
-- Vitals sensors are the 3rd object in each room (k=3 in the objects insert
-- above), so their object_id is 'OBJ-' || lpad((room_id*3)::text, 5, '0').
-- FDS sensors are the 2nd object (object_id ends in (room_id*3 - 1)).
--
-- Determinism: setseed() pins random() so every re-apply produces the same
-- numbers — test answers stay reproducible.

-- Re-runnable: clear our slice of sensor tables. No CASCADE needed; these
-- tables don't have anything FKing into them. activity_log / insights /
-- notifications / incidents were already cleared by Phase A's
-- TRUNCATE ... CASCADE (they FK into the seeded core tables) — re-listing
-- them here is harmless and keeps Phase C self-contained.
TRUNCATE TABLE
    public.vitals,
    public.sleep_sessions,
    public.wellness_metrics,
    public.activity_log,
    public.incidents,
    public.notifications,
    public.insights,
    public.ambience,
    public.on_bed
RESTART IDENTITY;

SELECT setseed(0.42);

-- C1. vitals — heart rate (hr, bpm) and respiration rate (rr, breaths/min).
-- 40 vitals boards × 15 days × 4 samples/day = 2,400 rows.
-- HR baseline varies per resident (65..85 bpm range), with small noise.
-- Canonical window: day d (0..14) is CURRENT_DATE - 1 - d, so the series
-- spans the 15 completed days [CURRENT_DATE-15 .. CURRENT_DATE-1] (ends
-- yesterday). Four samples sit inside each day at 02:00 / 08:00 / 14:00 / 20:00.
INSERT INTO public.vitals (ingestion_time, hr, rr, board)
SELECT
    (CURRENT_DATE - 1 - d)::timestamp + INTERVAL '2 hours' + (INTERVAL '6 hours' * h),
    ROUND((65 + (rid % 21) + (random() * 8 - 4))::numeric, 1),
    ROUND((13 + (random() * 6))::numeric, 1),
    'OBJ-' || lpad((rid * 3)::text, 5, '0')
FROM generate_series(1, 40) AS rid,
     generate_series(0, 14) AS d,
     generate_series(0, 3)  AS h;

-- C2. sleep_sessions — last 15 nights, 4 stage segments per night
-- (light → deep → rem → awake). 40 boards × 15 nights × 4 stages = 2,400 rows.
-- Night d (0..14) begins the evening of CURRENT_DATE - 1 - d, so a night is
-- labelled by the evening it starts and the 15 nights span the same
-- [CURRENT_DATE-15 .. CURRENT_DATE-1] window as every other Phase C table.
-- Night d=0 is "last night" (CURRENT_DATE-1 22:00 → CURRENT_DATE 06:00).
--
-- Total sleep VARIES per resident and night so "when did X sleep less/most?"
-- and the nightly trend are meaningful instead of a flat number. Each stage's
-- duration (in minutes) is drawn from the pinned setseed(0.42) random()
-- stream — irregular-looking but reproducible across re-seeds, same as the
-- vitals/wellness tables. The four durations are picked ONCE per night in the
-- `dur` LATERAL and reused, so each stage starts exactly where the previous
-- one ended (offset_m = running sum) and the segments stay contiguous:
--   light  ~1.5–2.0h,  deep  ~1.5–4.0h,  rem  ~1.25–2.0h,  awake ~20–60m
-- → total asleep (light + deep + rem, awake excluded) lands around 4.5–8h.
-- The per-night random draws live in subquery `n` (one row per resident/night,
-- random() in its target list over the generate_series — the same shape the
-- vitals insert uses, which guarantees a fresh draw per row). The 4 stages are
-- then LATERAL-joined onto each night and reuse n's already-computed minutes,
-- so a night's segments stay contiguous. (Drawing random() in a non-correlated
-- LATERAL instead would be folded to a single value and repeat every night.)
INSERT INTO public.sleep_sessions
    (board, sleep_stage, start_duration, end_duration, sleep_type, created_at, updated_at)
SELECT
    'OBJ-' || lpad((n.rid * 3)::text, 5, '0'),
    stage_data.stage,
    n.base + (stage_data.offset_m * INTERVAL '1 minute'),
    n.base + ((stage_data.offset_m + stage_data.dur_m) * INTERVAL '1 minute'),
    'night'::public.sleeptypeenum,
    now(), now()
FROM (
    SELECT
        rid, d,
        (CURRENT_DATE - d - 1)::timestamp + INTERVAL '22 hours' AS base,
        round(90 + random() * 30)::int  AS light_m,   -- 90–120 min
        round(90 + random() * 150)::int AS deep_m,    -- 90–240 min
        round(75 + random() * 45)::int  AS rem_m,     -- 75–120 min
        round(20 + random() * 40)::int  AS awake_m    -- 20–60 min
    FROM generate_series(1, 40) AS rid,
         generate_series(0, 14) AS d
) n,
LATERAL (VALUES
    ('light'::public.sleepstageenum, 0,                                  n.light_m),
    ('deep'::public.sleepstageenum,  n.light_m,                          n.deep_m),
    ('rem'::public.sleepstageenum,   n.light_m + n.deep_m,               n.rem_m),
    ('awake'::public.sleepstageenum, n.light_m + n.deep_m + n.rem_m,     n.awake_m)
) AS stage_data(stage, offset_m, dur_m);

-- C3. wellness_metrics — per-day aggregated score per board per type
-- (sleep, activity, vitals, environment). 40 × 15 × 4 = 2,400 rows.
-- Score 50..95, varies per resident, day, and metric type.
INSERT INTO public.wellness_metrics
    (board, type, time_interval, score, date, start_time, end_time)
SELECT
    'OBJ-' || lpad((rid * 3)::text, 5, '0'),
    t.metric_type,
    'daily'::public.timeintervalenum,
    ROUND((50 + (rid % 11) * 3 + d + (random() * 20))::numeric, 1),
    CURRENT_DATE - 1 - d,
    (CURRENT_DATE - 1 - d)::timestamp,
    (CURRENT_DATE - 1 - d)::timestamp + INTERVAL '23 hours 59 minutes 59 seconds'
FROM generate_series(1, 40) AS rid,
     generate_series(0, 14) AS d,
     (VALUES
       ('sleep'::public.summarytypeenum),
       ('activity'::public.summarytypeenum),
       ('vitals'::public.summarytypeenum),
       ('environment'::public.summarytypeenum)
     ) AS t(metric_type);

-- C4. activity_log — three activity sessions per resident per day
-- (sleeping overnight, active mid-morning, walking in the afternoon).
-- 40 residents × 15 days × 3 sessions = 1,800 rows.
-- resident_id is FK to resident_profile.id (direct after migration).
INSERT INTO public.activity_log
    (object_id, location, resident_id, status, start_time, end_time, created_at, updated_at)
SELECT
    'OBJ-' || lpad((rid * 3)::text, 5, '0'),
    'bedroom',
    rid,
    activity.status,
    (CURRENT_DATE - 1 - d)::timestamp + (INTERVAL '1 hour' * activity.start_h),
    (CURRENT_DATE - 1 - d)::timestamp + (INTERVAL '1 hour' * activity.end_h),
    now(), now()
FROM generate_series(1, 40) AS rid,
     generate_series(0, 14) AS d,
     (VALUES
       ('sleeping'::public.statusenum, 22, 30),   -- 10pm to 6am next day
       ('active'::public.statusenum,    8, 11),   -- 8am to 11am
       ('walking'::public.statusenum,  16, 17)    -- 4pm to 5pm
     ) AS activity(status, start_h, end_h);

-- C5. incidents — 30 fall / movement / out-of-room events spread across the
-- 15 completed days (2 per day), so "any incidents this week/fortnight"
-- returns a full window of history. object_id points at the room's radar device.
-- Anchored to (CURRENT_DATE - days_ago) with days_ago 1..15 so events fall on
-- whole, completed days [CURRENT_DATE-15 .. CURRENT_DATE-1] like every other
-- Phase C table; the two unresolved (status=false) alerts sit on day 1
-- (yesterday) so "active/unresolved alerts" still has something to show.
INSERT INTO public.incidents
    (room_id, event_category, event_outcome, event_time, status, object_id,
     object_type, escalation_level, created_at, updated_at)
SELECT
    incident.room_id,
    incident.category,
    incident.outcome,
    (CURRENT_DATE - incident.days_ago)::timestamp + (INTERVAL '1 hour' * incident.hour_of_day),
    incident.status,
    'OBJ-' || lpad((incident.room_id * 3)::text, 5, '0'),
    'sensor',
    incident.escalation,
    now(), now()
FROM (VALUES
    -- (room_id, category, outcome, days_ago (1..15), hour_of_day, status (true=resolved), escalation_level)
    (12, 'fall_alert'::public.eventcategoryenum,      'in progress',           1,  3, false, 1),
    (33, 'out_of_room'::public.eventcategoryenum,     'in progress',           1, 23, false, 1),
    (1,  'fall_alert'::public.eventcategoryenum,      'resolved by caregiver', 2, 14, true,  0),
    (27, 'confirmed_fall'::public.eventcategoryenum,  'admitted to hospital',  2, 11, true,  2),
    (15, 'out_of_bed'::public.eventcategoryenum,      'returned to bed',       3,  6, true,  0),
    (5,  'movement'::public.eventcategoryenum,        'normal movement',       3,  9, true,  0),
    (8,  'confirmed_fall'::public.eventcategoryenum,  'admitted to hospital',  4, 20, true,  1),
    (11, 'out_of_bed'::public.eventcategoryenum,      'returned to bed',       4,  5, true,  0),
    (22, 'fall_alert'::public.eventcategoryenum,      'resolved by caregiver', 5,  4, true,  0),
    (19, 'suspected_alert'::public.eventcategoryenum, 'resolved by caregiver', 5, 22, true,  0),
    (38, 'fall_alert'::public.eventcategoryenum,      'resolved by caregiver', 6,  9, true,  0),
    (3,  'out_of_bed'::public.eventcategoryenum,      'returned to bed',       6,  2, true,  0),
    (7,  'movement'::public.eventcategoryenum,        'normal movement',       7, 13, true,  0),
    (30, 'suspected_alert'::public.eventcategoryenum, 'resolved by caregiver', 7, 18, true,  0),
    (16, 'fall_alert'::public.eventcategoryenum,      'resolved by caregiver', 8,  7, true,  0),
    (24, 'out_of_bed'::public.eventcategoryenum,      'returned to bed',       8, 15, true,  0),
    (9,  'suspected_alert'::public.eventcategoryenum, 'resolved by caregiver', 9, 21, true,  0),
    (35, 'movement'::public.eventcategoryenum,        'normal movement',       9, 10, true,  0),
    (4,  'fall_alert'::public.eventcategoryenum,      'resolved by caregiver',10,  3, true,  0),
    (28, 'confirmed_fall'::public.eventcategoryenum,  'admitted to hospital', 10, 19, true,  2),
    (13, 'out_of_room'::public.eventcategoryenum,     'returned to room',      11,  1, true,  0),
    (20, 'out_of_bed'::public.eventcategoryenum,      'returned to bed',       11, 12, true,  0),
    (6,  'fall_alert'::public.eventcategoryenum,      'resolved by caregiver', 12,  8, true,  0),
    (31, 'suspected_alert'::public.eventcategoryenum, 'resolved by caregiver', 12, 23, true,  0),
    (17, 'movement'::public.eventcategoryenum,        'normal movement',       13, 16, true,  0),
    (25, 'fall_alert'::public.eventcategoryenum,      'resolved by caregiver', 13,  5, true,  0),
    (10, 'out_of_bed'::public.eventcategoryenum,      'returned to bed',       14,  2, true,  0),
    (37, 'confirmed_fall'::public.eventcategoryenum,  'admitted to hospital', 14, 20, true,  1),
    (14, 'fall_alert'::public.eventcategoryenum,      'resolved by caregiver', 15, 11, true,  0),
    (29, 'movement'::public.eventcategoryenum,        'normal movement',       15, 14, true,  0)
) AS incident(room_id, category, outcome, days_ago, hour_of_day, status, escalation);

-- C6. notifications — one per incident, with resident_id pulled from the
-- 1:1 room↔resident mapping (resident_id = room_id in the seed). Generic
-- message text so a future rename of resident names doesn't desync.
INSERT INTO public.notifications
    (event_category, event_time, resident_id, room_id, status, message, created_at, updated_at)
SELECT
    notif.category,
    (CURRENT_DATE - notif.days_ago)::timestamp + (INTERVAL '1 hour' * notif.hour_of_day),
    notif.room_id,   -- room_resident_mapping is 1:1, resident_id == room_id
    notif.room_id,
    notif.status,
    notif.message,
    now(), now()
FROM (VALUES
    -- mirrors the C5 incidents, same days/hours/status so the two tables agree
    (12, 'fall_alert'::public.eventcategoryenum,      false, 'Fall alert in progress',                     1,  3),
    (33, 'out_of_room'::public.eventcategoryenum,     false, 'Resident out of room (alert active)',        1, 23),
    (1,  'fall_alert'::public.eventcategoryenum,      true,  'Fall alert resolved by caregiver',           2, 14),
    (27, 'confirmed_fall'::public.eventcategoryenum,  true,  'Confirmed fall, admitted to hospital',       2, 11),
    (15, 'out_of_bed'::public.eventcategoryenum,      true,  'Resident returned to bed safely',            3,  6),
    (5,  'movement'::public.eventcategoryenum,        true,  'Movement detected (normal pattern)',         3,  9),
    (8,  'confirmed_fall'::public.eventcategoryenum,  true,  'Confirmed fall, ambulance dispatched',       4, 20),
    (11, 'out_of_bed'::public.eventcategoryenum,      true,  'Resident returned to bed safely',            4,  5),
    (22, 'fall_alert'::public.eventcategoryenum,      true,  'Fall alert resolved by caregiver',           5,  4),
    (19, 'suspected_alert'::public.eventcategoryenum, true,  'Suspected fall — confirmed false positive',  5, 22),
    (38, 'fall_alert'::public.eventcategoryenum,      true,  'Fall alert resolved by caregiver',           6,  9),
    (3,  'out_of_bed'::public.eventcategoryenum,      true,  'Resident returned to bed safely',            6,  2),
    (7,  'movement'::public.eventcategoryenum,        true,  'Movement detected (normal pattern)',         7, 13),
    (30, 'suspected_alert'::public.eventcategoryenum, true,  'Suspected fall — confirmed false positive',  7, 18),
    (16, 'fall_alert'::public.eventcategoryenum,      true,  'Fall alert resolved by caregiver',           8,  7),
    (24, 'out_of_bed'::public.eventcategoryenum,      true,  'Resident returned to bed safely',            8, 15),
    (9,  'suspected_alert'::public.eventcategoryenum, true,  'Suspected fall — confirmed false positive',  9, 21),
    (35, 'movement'::public.eventcategoryenum,        true,  'Movement detected (normal pattern)',         9, 10),
    (4,  'fall_alert'::public.eventcategoryenum,      true,  'Fall alert resolved by caregiver',          10,  3),
    (28, 'confirmed_fall'::public.eventcategoryenum,  true,  'Confirmed fall, admitted to hospital',      10, 19),
    (13, 'out_of_room'::public.eventcategoryenum,     true,  'Resident returned to room safely',          11,  1),
    (20, 'out_of_bed'::public.eventcategoryenum,      true,  'Resident returned to bed safely',           11, 12),
    (6,  'fall_alert'::public.eventcategoryenum,      true,  'Fall alert resolved by caregiver',          12,  8),
    (31, 'suspected_alert'::public.eventcategoryenum, true,  'Suspected fall — confirmed false positive', 12, 23),
    (17, 'movement'::public.eventcategoryenum,        true,  'Movement detected (normal pattern)',        13, 16),
    (25, 'fall_alert'::public.eventcategoryenum,      true,  'Fall alert resolved by caregiver',          13,  5),
    (10, 'out_of_bed'::public.eventcategoryenum,      true,  'Resident returned to bed safely',           14,  2),
    (37, 'confirmed_fall'::public.eventcategoryenum,  true,  'Confirmed fall, admitted to hospital',      14, 20),
    (14, 'fall_alert'::public.eventcategoryenum,      true,  'Fall alert resolved by caregiver',          15, 11),
    (29, 'movement'::public.eventcategoryenum,        true,  'Movement detected (normal pattern)',        15, 14)
) AS notif(room_id, category, status, message, days_ago, hour_of_day);

-- C7. insights — 3 short generated insights per resident (sleep, activity,
-- vitals). 40 residents × 3 types = 120 rows. Dated to the latest completed
-- day (CURRENT_DATE - 1) so "latest insight for X" stays inside the same
-- [CURRENT_DATE-15 .. CURRENT_DATE-1] window as the rest of Phase C.
INSERT INTO public.insights
    (resident_id, board, type, priority, date, insight, created_at, updated_at)
SELECT
    rid,
    'OBJ-' || lpad((rid * 3)::text, 5, '0'),
    t.metric_type,
    t.priority,
    CURRENT_DATE - 1,
    t.text,
    now(), now()
FROM generate_series(1, 40) AS rid,
     (VALUES
       ('sleep'::public.insighttypeenum,    'mid'::public.insightpriorityenum,
        'Sleep quality within normal range. Average deep sleep ~3h.'),
       ('activity'::public.insighttypeenum, 'low'::public.insightpriorityenum,
        'Activity levels consistent with recent baseline.'),
       ('vitals'::public.insighttypeenum,   'low'::public.insightpriorityenum,
        'Heart rate and respiration within healthy bands.')
     ) AS t(metric_type, priority, text);

-- C8. ambience — 40 boards × 15 days × 4 samples/day = 2,400 rows.
-- temp 22-29°C, humidity 45-65%. Samples sit at 00:00 / 06:00 / 12:00 / 18:00
-- of each completed day [CURRENT_DATE-15 .. CURRENT_DATE-1], matching the rest
-- of Phase C instead of the previous "last 24 hours only" window.
INSERT INTO public.ambience (ingestion_time, temp, humidity, board, location)
SELECT
    (CURRENT_DATE - 1 - d)::timestamp + (INTERVAL '6 hours' * h),
    ROUND((22 + (rid % 4) + (random() * 3))::numeric, 1),
    ROUND((45 + (random() * 20))::numeric, 1),
    'OBJ-' || lpad((rid * 3)::text, 5, '0'),
    'bedroom'
FROM generate_series(1, 40) AS rid,
     generate_series(0, 14) AS d,
     generate_series(0, 3)  AS h;

-- C9. on_bed — bed-state events: in bed at 22:00, out of bed at 06:00 the
-- next morning. 40 boards × 15 days × 2 events = 1,200 rows. Anchored to the
-- same completed-day window as the rest of Phase C: night d (0..14) begins the
-- evening of CURRENT_DATE - 1 - d.
INSERT INTO public.on_bed (ingestion_time, "time", board, location, on_bed)
SELECT
    (CURRENT_DATE - 1 - d)::timestamp + (CASE WHEN b.in_bed THEN INTERVAL '22 hours' ELSE INTERVAL '30 hours' END),
    to_char((CURRENT_DATE - 1 - d)::timestamp + (CASE WHEN b.in_bed THEN INTERVAL '22 hours' ELSE INTERVAL '30 hours' END), 'HH24:MI'),
    'OBJ-' || lpad((rid * 3)::text, 5, '0'),
    'bedroom',
    b.in_bed
FROM generate_series(1, 40) AS rid,
     generate_series(0, 14) AS d,
     (VALUES (22, true), (6, false)) AS b(hour, in_bed);

-- ===========================================================================
-- D. View rebuild — vw_resident_sensor against the new model.
-- Removes the LEFT JOIN to users entirely; resident attributes (name, dob,
-- gender, flat_number, no_of_falls, fall_alert) all come from resident_profile.
-- ===========================================================================
CREATE OR REPLACE VIEW public.vw_resident_sensor AS
SELECT
    o.id              AS object_pk,
    o.object_id       AS object_id,
    o.object_type     AS object_type,
    o.status          AS object_status,
    o.is_active       AS object_is_active,
    o.location        AS object_location,
    o.device_status   AS device_status,
    r.id              AS room_id,
    r.room_name       AS room_name,
    r.room_pos        AS room_pos,
    c.id              AS community_id,
    c.name            AS community_name,
    c.organisation_id AS organisation_id,
    rrm.resident_id   AS resident_id,
    rp.name           AS resident_name,
    rp.flat_number    AS resident_flat,
    rp.dob            AS resident_dob,
    rp.gender         AS resident_gender,
    rp.no_of_falls    AS resident_no_of_falls,
    rp.fall_alert     AS resident_fall_alert
FROM public.objects o
INNER JOIN public.rooms r
        ON r.id = o.room_id
       AND COALESCE(r.is_deleted, false) = false
INNER JOIN public.community c
        ON c.id = r.community_id
       AND COALESCE(c.is_deleted, false) = false
LEFT JOIN public.room_resident_mapping rrm
        ON rrm.room_id = r.id
       AND COALESCE(rrm.is_deleted, false) = false
LEFT JOIN public.resident_profile rp
        ON rp.id = rrm.resident_id
       AND COALESCE(rp.is_deleted, false) = false
WHERE COALESCE(o.is_deleted, false) = false;

COMMIT;
