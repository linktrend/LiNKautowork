/** The controlled ways an Automation Architect may prepare a candidate. */
export type ArchitectMode = 'create' | 'adapt' | 'compose' | 'refine';

/** A source form accepted into the quarantined intake process. */
export type SourceKind =
  | 'n8n_export'
  | 'make_blueprint'
  | 'zapier_export'
  | 'github_repository'
  | 'open_source_project'
  | 'documented_flow'
  | 'manual_specification';

/** A licence conclusion made before the source can influence a candidate. */
export type LicenceState = 'cleared' | 'not_applicable' | 'unknown' | 'restricted';

/** A source's handling in the source-to-target mapping. */
export type MappingAction = 'reused_as_reference' | 'reimplemented' | 'discarded';

/** One redacted source component that may be mapped to a candidate. */
export interface SourceComponent {
  readonly reference: string;
  readonly kind: 'trigger' | 'step' | 'condition' | 'output' | 'integration' | 'other';
  readonly capability?: string;
  readonly sideEffect?: string;
}

/** A source submitted to the Architect. `content` is quarantined input and never copied to a report. */
export interface ApprovedSource {
  readonly sourceId: string;
  readonly kind: SourceKind;
  readonly locator: string;
  readonly revision: string;
  readonly content: string;
  readonly licence: {
    readonly identifier: string;
    readonly state: LicenceState;
  };
  readonly components: readonly SourceComponent[];
}

/** A required result from the target automation. */
export interface ExpectedOutput {
  readonly description: string;
  readonly fields: readonly string[];
}

/** The immutable target metadata needed to prepare a GAP candidate. */
export interface CandidateTarget {
  readonly automationId: string;
  readonly version: string;
  readonly displayName: string;
  readonly owningProgram: string;
  readonly classification: 'internal_only' | 'commercial_capable';
  readonly ownerKind: 'internal_system' | 'commercial_product' | 'shared_internal';
  readonly bindingOperations: readonly string[];
  readonly sourceGitSha: string;
}

/** Requirements that the Architect can turn into an inactive candidate package. */
export interface ArchitectRequirements {
  readonly summary: string;
  readonly expectedOutput?: ExpectedOutput;
  readonly triggerMode: 'webhook' | 'schedule' | 'event' | 'manual' | 'hybrid';
  readonly resultMode: 'synchronous_response' | 'callback' | 'event' | 'none';
  readonly sideEffects: readonly string[];
  readonly requiredCapabilities: readonly string[];
  readonly requiredSecretReferences: readonly { readonly secretRef: string; readonly purpose: string }[];
  readonly redactedEvidence?: readonly EvidenceReference[];
}

/** A redacted evidence reference, never a raw incident, customer, or secret payload. */
export interface EvidenceReference {
  readonly reference: string;
  readonly kind: 'evaluation' | 'incident' | 'telemetry' | 'api_change' | 'approved_requirement';
  readonly digest?: string;
}

/** The machine-readable request that is the sole input to candidate preparation. */
export interface ArchitectRequest {
  readonly taskId: string;
  readonly mode: ArchitectMode;
  readonly target: CandidateTarget;
  readonly approvedSources: readonly ApprovedSource[];
  readonly requirements: ArchitectRequirements;
  readonly exclusions: readonly string[];
  readonly runtime: {
    readonly engine: 'n8n';
    readonly n8nVersion: string;
    readonly supportedCapabilities: readonly string[];
  };
  readonly evidenceReferences: readonly EvidenceReference[];
  readonly requestProductionMutation?: boolean;
  readonly requestedStatus?: 'candidate' | 'certified' | 'deployed';
  readonly resumeFromTaskId?: string;
}

/** A stop condition found deterministically before package generation. */
export interface StopCondition {
  readonly code:
    | 'DIRECT_PRODUCTION_MUTATION'
    | 'SELF_CERTIFICATION_REQUEST'
    | 'UNKNOWN_LICENCE'
    | 'RESTRICTED_LICENCE'
    | 'EMBEDDED_SECRET_OR_CUSTOMER_DATA'
    | 'MISSING_EXPECTED_OUTPUT'
    | 'MISSING_GSM_REFERENCE_DESIGN'
    | 'UNSUPPORTED_SIDE_EFFECT'
    | 'UNAVAILABLE_RUNTIME_CAPABILITY'
    | 'MISSING_APPROVED_SOURCE'
  | 'INVALID_MODE_SOURCE_COUNT'
  | 'REFINE_EVIDENCE_REQUIRED'
  | 'INVALID_REQUEST'
  | 'INVALID_SOURCE_MAP'
  | 'UNSUPPORTED_RESULT_MODE';
  readonly message: string;
  readonly sourceId?: string;
}

/** A source-to-target record retained in every candidate report and provenance file. */
export interface SourceMapEntry {
  readonly sourceId: string;
  readonly sourceComponentRef: string;
  readonly targetComponentRef: string;
  readonly action: MappingAction;
  readonly reason: string;
}

/** Safe metadata extracted from a quarantined source. */
export interface IntakeAssessment {
  readonly sourceId: string;
  readonly contentDigest: string;
  readonly archiveDigest?: string;
  readonly detectedNodeTypes: readonly string[];
  readonly componentCount: number;
  readonly secretFindingCount: number;
  readonly customerDataFindingCount: number;
  readonly status: 'assessed' | 'rejected';
}

/** Result reported by the WP-02 validator adapter. */
export interface CandidateValidationResult {
  readonly status: 'passed' | 'failed' | 'runner_unavailable';
  readonly command: string;
  readonly findings: readonly string[];
  readonly receiptRef?: string;
}

/** WP-02 is injected rather than imported, preserving its ownership boundary. */
export interface CandidateValidator {
  validate(candidate: CandidatePackage): Promise<CandidateValidationResult>;
}

/** An inactive, in-memory Golden Automation Package candidate. */
export interface CandidatePackage {
  readonly root: string;
  readonly files: Readonly<Record<string, string>>;
  readonly packageDigest: string;
  readonly workflowDigest: string;
}

/** Complete candidate-only branch/PR report. */
export interface ArchitectReport {
  readonly schemaVersion: '0.1';
  readonly taskId: string;
  readonly mode: ArchitectMode;
  readonly status: 'candidate' | 'stopped';
  readonly target: { readonly automationId: string; readonly version: string };
  readonly intake: readonly IntakeAssessment[];
  readonly stopConditions: readonly StopCondition[];
  readonly sourceMap: readonly SourceMapEntry[];
  readonly candidate?: CandidatePackage;
  readonly validation: CandidateValidationResult;
  readonly regressionAdditions: readonly string[];
  readonly productionMutationPerformed: false;
  readonly certificationPerformed: false;
  readonly deploymentPerformed: false;
  readonly resumeKey: string;
}
