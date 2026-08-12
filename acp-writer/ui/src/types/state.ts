export interface CarePlanComposerState {
  run_id?: string;
  output_dir?: string;
  ips_bundle?: Record<string, unknown>;
  patient_reference?: string;
  patient_demographics?: Record<string, unknown>;
  condition_codes?: Array<Record<string, string>>;
  medication_codes?: Array<Record<string, string>>;
  allergy_codes?: Array<Record<string, string>>;
  applicable_cpgs?: Array<Record<string, unknown>>;
  applicable_dmn_models?: Array<Record<string, unknown>>;
  dmn_dependency_graph?: string[][];
  dmn_results?: Array<Record<string, unknown>>;
  recommendations?: Array<Record<string, unknown>>;
  planning_brief?: Record<string, unknown>;
  brief_review_count?: number;
  brief_review_feedback?: string;
  fhir_bundle?: Record<string, unknown>;
  terminology_issues?: Array<Record<string, string>>;
  syntax_errors?: string[];
  fhir_review_count?: number;
  fhir_review_feedback?: string;
  fhir_server_response?: Record<string, unknown>;
  careplan_id?: string;
  delivery_status?: string;
}
