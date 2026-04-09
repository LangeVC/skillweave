# Project Patterns & Guidelines: AI Meeting Notes Summarizer

## Architecture Patterns
- [Patterns discovered during development]

## Code Standards
- **Frontend**: React with TypeScript, functional components, hooks
- **Backend**: Node.js/Express, async/await, error handling middleware
- **Styling**: Tailwind CSS utility classes
- **Testing**: Jest for unit tests, Cypress for E2E
- **File Structure**: Feature-based organization

## Gotchas & Solutions
- [Common issues and their solutions]

## Integration Notes
- **OpenAI Whisper**: Rate limits, audio format requirements
- **WebRTC**: Browser compatibility, permission handling
- **WebSocket**: Connection management, reconnection logic

## Best Practices
### Audio Processing
1. Sample rate: 16kHz for Whisper
2. Format: WAV or MP3
3. Chunk size: 10-30 seconds for real-time

### Transcription
1. Speaker diarization works best with 2-5 speakers
2. Punctuation improves with temperature=0
3. Retry logic for API rate limits

### Security
1. JWT tokens expire in 24 hours
2. Audio encryption at rest and in transit
3. GDPR compliance for EU users

## Project-Specific Decisions
- **Database**: PostgreSQL for metadata, S3 for audio files
- **Deployment**: Docker containers on AWS ECS
- **Monitoring**: CloudWatch metrics, Sentry for errors

## Performance Optimization
- Audio compression before transmission
- Caching of frequent transcriptions
- Lazy loading for meeting history

## Testing Strategy
- Unit tests for business logic
- Integration tests for API endpoints
- E2E tests for user workflows
- Load tests for concurrent meetings

## Development Workflow
1. Create feature branch from main
2. Write tests first (TDD)
3. Implement feature
4. Run lint, typecheck, tests
5. Submit PR with description

## Deployment Checklist
- [ ] Run all tests
- [ ] Update environment variables
- [ ] Database migrations (if any)
- [ ] Backup current deployment
- [ ] Deploy to staging
- [ ] Smoke tests
- [ ] Deploy to production
- [ ] Monitor metrics

## Troubleshooting
### Common Issues
1. **Microphone permissions**: Guide users to browser settings
2. **Poor audio quality**: Suggest headset, quiet environment
3. **Transcription failures**: Check API key, network connection

### Debug Commands
```bash
# Check audio levels
node scripts/check-audio.js

# Test transcription
node scripts/test-transcription.js sample.wav

# Monitor WebSocket connections
node scripts/ws-monitor.js
```

## Knowledge Base
*This section will grow as we encounter and solve problems during development.*